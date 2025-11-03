# Python OpenShift CronJob Operator

This project is a simple OpenShift/Kubernetes operator built with Python and the kopf framework. It manages a set of CronJob resources across multiple namespaces, based on a single CronJobManager custom resource.

## Features

* Manages multiple CronJob resources from a single manifest.  
* Deploys CronJobs to different target namespaces.  
* Features a globalSuspend "kill switch" to immediately suspend all managed CronJobs (No new jobs will be kicked off).  
  * NOTE: If there is a Job running when the kill switch is thrown to ON, it will not be stopped by this process.
* Automatically cleans up CronJobs that are removed from the CronJobManager spec.

## Prerequisites

* Kubernetes cluster, this was tested against Openshift (ROSA) v4.18
* `oc` CLI connected to an OpenShift cluster with cluster-admin privileges.  
* `podman` installed and running, with permissions to build and push images.  
* Python 3.8+ and pip installed locally.
* (Optional) The following libraries pulled for your local IDE to reference:

    ```console
    pip install kopf==1.35.4 kubernetes==28.1.0
    ```

* Ensure your OCP registry is exposed

  1. See if the default route is established (returns a URL if successful)

        ```console
        oc get route default-route -n openshift-image-registry -o jsonpath='{.spec.host}'
        ```

  1. If no URL is returned expose the registry

        ```console
        oc patch configs.imageregistry.operator.openshift.io/cluster --patch '{"spec":{"defaultRoute":true}}' --type=merge
        ```

        Test with prior command

## Step-by-Step Deployment Guide

### 1\. Set Up Your Project

Pull down from Github

```console
git clone git@github.com:billwheatley/cronjob-operator-poc.git
```

### 2\. Create Namespaces

The operator will live in its own namespace (my-operator-system), and the example cronjobs will be deployed to two other namespaces (target-ns-a and target-ns-b).

Create all three:

```console
oc create namespace my-operator-system  
oc create namespace target-ns-a  
oc create namespace target-ns-b
```

### 3\. Build and Push the Operator Image

```console
./build-deploy.sh
```

### 4\. Deploy the Operator

1. Apply the Custom Resource Definition (CRD)  
This tells the cluster about our new 'CronJobManager' resource type.

    ```console
    oc apply -f crd.yaml
    ```

1. Apply the operator's Deployment, ServiceAccount, and Roles  
This starts the operator pod.  

    ```console
    oc apply -f operator-deployment.yaml
    ```

    Check that the operator is running:

    ```console
    oc get pods -n my-operator-system  
    ```

    Should see a pod named 'my-cron-operator-...' in a 'Running' state.

    You can also view its logs to see it start up:

    ```console
    oc logs -n my-operator-system -l app=my-cron-operator -f
    ```

### 5\. Use the Operator: Deploy CronJobs

With the operator running, you can now create a CronJobManager resource. The operator will see this and immediately create the CronJobs you've defined.

1. Apply the example manifest  

    ```console
    oc apply -f example-manager.yaml
    ```

1. The operator will now create the 5 example cronjobs.

    You can verify they were created:

    Check in namespace 'target-ns-a'  

    ```console
    oc get cronjobs -n target-ns-a
    ```

    Check in namespace 'target-ns-b'  

    ```console
    oc get cronjobs -n target-ns-b
    ```

    You should see the jobs listed, with their correct schedules and SUSPEND set to False.

## How to Use the "Kill Switch"

To stop all jobs, you just patch the `CronJobManager` resource.

### To DISABLE (suspend) all jobs:

```console
oc patch cronjobmanager my-cron-set \  
  -n my-operator-system \
  --type merge \
  -p '{"spec":{"globalSuspend":true}}'
```

To verify watch the operator logs (oc logs ... \-f), you'll see it detect the change.

Now, check the CronJobs again. Their SUSPEND column will be True.  

```console
oc get cronjobs -n target-ns-a  
oc get cronjobs -n target-ns-b
```

### To RE-ENABLE all jobs:

```console
oc patch cronjobmanager my-cron-set \
  -n my-operator-system \
  --type merge \
  -p '{"spec":{"globalSuspend":false}}'
```

The operator will again detect this and update all CronJobs to set suspend: false.

## Cleanup

To remove everything you've deployed:

```console
oc delete -f example-manager.yaml  
oc delete -f operator-deployment.yaml  
oc delete -f crd.yaml  
oc delete namespace my-operator-system  
oc delete namespace target-ns-a  
oc delete namespace target-ns-b
```

## Misc Troubleshooting Commands

### Force Operator Pod Restart

Useful for certain deployment changes that don't get picked up

```console
oc delete pod -n my-operator-system -l app=my-cron-operator
```

### Checking Events in the target namespaces

Useful if CornJobs are not showing up after operator deploy

```console
oc get events -n target-ns-a |less
oc get events -n target-ns-b |less
```
