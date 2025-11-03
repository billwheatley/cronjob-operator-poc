# Use a slim Python base image
FROM python:3.9-slim

WORKDIR /src

# Install kopf and the kubernetes client
# We pin versions for stable, reproducible builds
RUN pip install kopf==1.35.4 kubernetes==28.1.0

# Copy the operator script into the image
COPY operator.py .

# Set the command to run kopf
# --verbose provides more logging
CMD ["kopf", "run", "operator.py", "--verbose"]
