# Kubernetes Deployment Guide

## Overview

This guide provides comprehensive instructions for deploying Document Intelligence AI on Kubernetes for production environments.

## Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured
- Helm 3.0+
- Container registry access
- TLS certificates for ingress

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│   Ingress       │────▶│   API Service   │────▶│   ChromaDB      │
│   Controller    │     │   (3 replicas)  │     │   StatefulSet   │
│                 │     │                 │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────┴────────┐
                        │                 │
                        ▼                 ▼
                ┌──────────────┐  ┌──────────────┐
                │              │  │              │
                │    Redis     │  │  ConfigMaps  │
                │  (HA Mode)   │  │   Secrets    │
                │              │  │              │
                └──────────────┘  └──────────────┘
```

## Deployment Steps

### 1. Create Namespace

```bash
kubectl create namespace document-intelligence
kubectl config set-context --current --namespace=document-intelligence
```

### 2. Create Secrets

```bash
# API Keys
kubectl create secret generic api-keys \
  --from-literal=openai-api-key=$OPENAI_API_KEY \
  --from-literal=api-auth-key=$API_AUTH_KEY

# TLS Certificates
kubectl create secret tls tls-secret \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key
```

### 3. Deploy ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  APP_ENV: "production"
  LOG_LEVEL: "INFO"
  CHUNK_SIZE: "1000"
  CHUNK_OVERLAP: "200"
  SEARCH_TOP_K: "10"
  SIMILARITY_THRESHOLD: "0.7"
  REDIS_URL: "redis://redis-service:6379"
  CHROMA_HOST: "chromadb-service"
  CHROMA_PORT: "8000"
```

### 4. Deploy Application

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: document-intelligence-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: document-intelligence-api
  template:
    metadata:
      labels:
        app: document-intelligence-api
    spec:
      containers:
      - name: api
        image: cbratkovics/document-intelligence-ai:latest
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: openai-api-key
        envFrom:
        - configMapRef:
            name: app-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: data
          mountPath: /app/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: data-pvc
```

### 5. Deploy ChromaDB StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: chromadb
spec:
  serviceName: chromadb-service
  replicas: 1
  selector:
    matchLabels:
      app: chromadb
  template:
    metadata:
      labels:
        app: chromadb
    spec:
      containers:
      - name: chromadb
        image: chromadb/chroma:latest
        ports:
        - containerPort: 8000
        volumeMounts:
        - name: chromadb-storage
          mountPath: /chroma/chroma
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
  volumeClaimTemplates:
  - metadata:
      name: chromadb-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 50Gi
```

### 6. Deploy Redis (HA Mode)

```bash
# Using Helm chart for Redis HA
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install redis bitnami/redis \
  --set auth.enabled=false \
  --set sentinel.enabled=true \
  --set replica.replicaCount=3
```

### 7. Configure Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  tls:
  - hosts:
    - api.document-intelligence.ai
    secretName: tls-secret
  rules:
  - host: api.document-intelligence.ai
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api-service
            port:
              number: 80
```

### 8. Configure Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: document-intelligence-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

## Monitoring Setup

### Deploy Prometheus Operator

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack
```

### Configure ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api-metrics
spec:
  selector:
    matchLabels:
      app: document-intelligence-api
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

## Security Considerations

1. **Network Policies**: Implement strict network policies
2. **Pod Security Standards**: Use restricted security context
3. **RBAC**: Configure proper role-based access control
4. **Secrets Management**: Use external secret operators
5. **Image Scanning**: Scan images before deployment

## Backup and Recovery

### Backup ChromaDB Data

```bash
# Create backup CronJob
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: chromadb-backup
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: busybox
            command:
            - /bin/sh
            - -c
            - tar -czf /backup/chromadb-\$(date +%Y%m%d-%H%M%S).tar.gz /data
            volumeMounts:
            - name: chromadb-storage
              mountPath: /data
            - name: backup-storage
              mountPath: /backup
          volumes:
          - name: chromadb-storage
            persistentVolumeClaim:
              claimName: chromadb-storage-chromadb-0
          - name: backup-storage
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
EOF
```

## Production Checklist

- [ ] TLS certificates configured
- [ ] Resource limits set appropriately
- [ ] Autoscaling configured
- [ ] Monitoring and alerting active
- [ ] Backup strategy implemented
- [ ] Network policies enforced
- [ ] Security scanning enabled
- [ ] Logging aggregation configured
- [ ] Disaster recovery plan tested

## Troubleshooting

### Common Issues

1. **Pod CrashLoopBackOff**
   ```bash
   kubectl logs -p <pod-name>
   kubectl describe pod <pod-name>
   ```

2. **Service Unavailable**
   ```bash
   kubectl get endpoints
   kubectl get svc
   ```

3. **Performance Issues**
   ```bash
   kubectl top pods
   kubectl top nodes
   ```

## Support

For production support: devops@document-intelligence.ai