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
      # The Droplet's private VPC IP isn't known at Terraform apply time
      # (it's assigned when the Droplet boots), so it's read here from
      # DigitalOcean's own metadata service rather than passed in from
      # Terraform — avoids a chicken-and-egg dependency between this
      # user_data script and the Droplet resource it configures.
      KAFKA_PRIVATE_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/private/0/ipv4/address)
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
