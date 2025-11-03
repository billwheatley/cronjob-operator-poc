# 1. Get the external registry host
#    This command finds the public route for the OpenShift registry.
export REGISTRY_HOST=$(oc get route default-route -n openshift-image-registry -o jsonpath='{.spec.host}')

if [ -z "$REGISTRY_HOST" ]; then
    echo "Error: Could not find the default route for the image registry."
    echo "Please ensure the image registry is exposed with a route."
    exit 1
fi

echo "Using registry host: $REGISTRY_HOST"

# 2. Log in to the OpenShift external registry
#    This command uses your 'oc' login token to authenticate with docker/podman.
oc whoami -t | podman login -u $(oc whoami) --password-stdin $REGISTRY_HOST

# 3. Build the image
#    We tag it with the external registry path and your operator's namespace.
podman build -t $REGISTRY_HOST/my-operator-system/my-cron-operator:latest .

# 4. Push the image
#    OpenShift will see this push and create/update an ImageStream in the
#    'my-operator-system' namespace, mapping it to the internal path.
podman push $REGISTRY_HOST/my-operator-system/my-cron-operator:latest

oc delete pod -n my-operator-system -l app=my-cron-operator