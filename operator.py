import kopf
import kubernetes
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# This is the core reconciliation logic
@kopf.on.resume('mygroup.example.com', 'v1', 'cronjobmanagers')
@kopf.on.update('mygroup.example.com', 'v1', 'cronjobmanagers')
@kopf.on.create('mygroup.example.com', 'v1', 'cronjobmanagers')
def reconcile_cronjobs(body, spec, meta, logger, **kwargs):
    """
    Main reconciliation loop.
    - 'body' is the full CronJobManager resource (the "parent").
    - 'spec' is the .spec field of the CronJobManager.
    - 'meta' is the .metadata field of the CronJobManager.
    """
    
    logger.info(f"Reconciling CronJobManager: {meta.get('name')}")
    try:
        api = kubernetes.client.BatchV1Api()
    except kubernetes.config.config_exception.ConfigException:
        # We are running inside the cluster
        kubernetes.config.load_incluster_config()
        api = kubernetes.client.BatchV1Api()

    # This label uniquely identifies all children of THIS CronJobManager instance
    # We use the parent's namespace and name to create a unique ID.
    manager_id = f"{meta['namespace']}_{meta['name']}"
    manager_label = "mygroup.example.com/manager"
    label_selector = f"{manager_label}={manager_id}"

    # Get desired state from the spec
    global_suspend = spec.get('globalSuspend', False)
    desired_jobs = {} # Use a dict for easy lookup: {(ns, name): job_def}
    
    for job_def in spec.get('jobs', []):
        key = (job_def['namespace'], job_def['name'])
        desired_jobs[key] = job_def

    logger.info(f"Desired state: {len(desired_jobs)} cronjobs. GlobalSuspend={global_suspend}")

    # === STEP 1: Create or Update all desired cronjobs ===
    for (target_ns, job_name), job_def in desired_jobs.items():
        try:
            # Build the CronJob manifest
            child_manifest = build_cronjob_manifest(job_def, global_suspend, meta, manager_id)

            # Try to get the existing job
            try:
                api.read_namespaced_cron_job(name=job_name, namespace=target_ns)
                # It exists, so patch it
                logger.info(f"Patching CronJob '{job_name}' in namespace '{target_ns}'...")
                api.patch_namespaced_cron_job(name=job_name, namespace=target_ns, body=child_manifest)
            
            except kubernetes.client.exceptions.ApiException as e:
                if e.status == 404:
                    # It doesn't exist, so create it
                    logger.info(f"Creating CronJob '{job_name}' in namespace '{target_ns}'...")
                    api.create_namespaced_cron_job(namespace=target_ns, body=child_manifest)
                else:
                    raise # Re-raise other API errors
        
        except Exception as e:
            logger.error(f"Error processing job '{job_name}' in '{target_ns}': {e}", exc_info=True)


    # === STEP 2: Find and Delete any orphaned cronjobs ===
    # This section is completely rewritten to be functional.
    logger.info("Checking for orphaned cronjobs...")
    try:
        # Get all cronjobs in all namespaces that this manager *might* own
        # Note: This requires cluster-wide 'list' permissions for cronjobs.
        current_jobs = api.list_cron_job_for_all_namespaces(label_selector=label_selector)
        
        current_job_keys = set()
        for job in current_jobs.items:
            key = (job.metadata.namespace, job.metadata.name)
            current_job_keys.add(key)
            
        # Find jobs that exist on the cluster but are NOT in our desired spec
        orphaned_keys = current_job_keys - set(desired_jobs.keys())
        
        if not orphaned_keys:
            logger.info("No orphaned cronjobs found.")
            return

        logger.info(f"Found {len(orphaned_keys)} orphaned cronjobs to delete...")
        
        for (target_ns, job_name) in orphaned_keys:
            try:
                logger.info(f"Deleting orphaned CronJob '{job_name}' from namespace '{target_ns}'...")
                api.delete_namespaced_cron_job(name=job_name, namespace=target_ns)
            except kubernetes.client.exceptions.ApiException as e:
                if e.status == 404:
                    # Already gone, which is fine
                    logger.warning(f"Orphaned job '{job_name}' in '{target_ns}' already deleted.")
                else:
                    logger.error(f"Error deleting orphan '{job_name}': {e}")
        
    except Exception as e:
        logger.error(f"Failed to list or delete orphaned cronjobs: {e}", exc_info=True)
        # We'll retry on the next reconciliation loop
    
    logger.info(f"Reconciliation complete for '{meta['name']}'.")


def build_cronjob_manifest(job_def: dict, global_suspend: bool, owner_meta: dict, manager_id_label_value: str) -> dict:
    """Helper function to build the CronJob body."""
    
    manager_label = "mygroup.example.com/manager"
    
    # Ensure labels exist in the pod template
    job_template = job_def.get('jobTemplate', {})
    job_template_spec = job_template.get('spec', {})
    pod_template = job_template_spec.get('template', {})
    pod_metadata = pod_template.get('metadata', {})
    if 'labels' not in pod_metadata:
        pod_metadata['labels'] = {}
    
    # Add a standard 'app' label to the pod
    pod_metadata['labels']['app'] = job_def['name']
    
    # Re-assemble the pod/job templates
    pod_template['metadata'] = pod_metadata
    job_template_spec['template'] = pod_template
    job_template['spec'] = job_template_spec
    
    return {
        'apiVersion': 'batch/v1',
        'kind': 'CronJob',
        'metadata': {
            'name': job_def['name'],
            'namespace': job_def['namespace'],
            'labels': {
                manager_label: manager_id_label_value,
                'app': job_def['name']
            }
        },
        'spec': {
            'schedule': job_def['schedule'],
            'suspend': global_suspend, # This is the kill switch!
            'jobTemplate': job_template, # Use the modified template
            'concurrencyPolicy': 'Forbid', # Prevents multiple jobs from running at once
            'successfulJobsHistoryLimit': 1,
            'failedJobsHistoryLimit': 1
        }
    }

