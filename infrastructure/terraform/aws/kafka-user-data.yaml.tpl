#cloud-config
package_update: true
packages:
  - docker.io

write_files:
  - path: /root/start-kafka.sh
    permissions: "0755"
    content: |
      #!/bin/sh
      set -eu
      # The instance's private VPC IP isn't known at Terraform apply time
      # (assigned when the instance boots), so it's read here from AWS's
      # own instance metadata service (IMDSv2 — token-based, the current
      # secure default) rather than passed in from Terraform — same
      # "avoid a chicken-and-egg dependency" reasoning the superseded
      # DigitalOcean Droplet's cloud-init used with DO's own metadata
      # service.
      IMDS_TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
        -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
      KAFKA_PRIVATE_IP=$(curl -s -H "X-aws-ec2-metadata-token: $${IMDS_TOKEN}" \
        http://169.254.169.254/latest/meta-data/local-ipv4)
      docker run -d --name kafka --restart unless-stopped \
        -p 9092:9092 \
        -e KAFKA_NODE_ID=1 \
        -e KAFKA_PROCESS_ROLES=broker,controller \
        -e KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
        -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://$${KAFKA_PRIVATE_IP}:9092 \
        -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
        -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
        -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
        -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
        -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
        -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
        -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 \
        -e KAFKA_LOG_DIRS=/var/lib/kafka/data \
        -v /var/lib/kafka/data:/var/lib/kafka/data \
        ${kafka_image}

runcmd:
  - systemctl enable docker
  - systemctl start docker
  - /root/start-kafka.sh
