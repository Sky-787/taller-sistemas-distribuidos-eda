#!/usr/bin/env bash
# Script de inicialización para LocalStack (AWS CLI local)
set -eo pipefail

echo "=========================================================="
echo "Configurando recursos AWS Event-Driven en LocalStack..."
echo "=========================================================="

AWS_REGION=us-east-1
ENDPOINT=http://localhost:4566

# 1. Crear Cola DLQ y Cola Principal SQS
awslocal sqs create-queue --queue-name catalog-events-dlq --region ${AWS_REGION}
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url ${ENDPOINT}/000000000000/catalog-events-dlq --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

awslocal sqs create-queue \
    --queue-name catalog-events \
    --region ${AWS_REGION} \
    --attributes "{\"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"

QUEUE_ARN=$(awslocal sqs get-queue-attributes --queue-url ${ENDPOINT}/000000000000/catalog-events --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)

# 2. Crear Regla en EventBridge
awslocal events put-rule \
    --name SpaceChangedRule \
    --event-pattern "{\"source\":[\"coworking.catalog\"],\"detail-type\":[\"SpaceChanged\"]}" \
    --state ENABLED \
    --region ${AWS_REGION}

# 3. Asociar SQS como Target de EventBridge
awslocal events put-targets \
    --rule SpaceChangedRule \
    --targets "Id"="CatalogEventsQueueTarget","Arn"="${QUEUE_ARN}" \
    --region ${AWS_REGION}

echo "Recursos Serverless EDA inicializados exitosamente en LocalStack!"
echo "Cola SQS: ${QUEUE_ARN}"
