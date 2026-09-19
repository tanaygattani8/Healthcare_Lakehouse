FROM apache/airflow:3.3.2
COPY requirements.txt .
# Pinning apache-airflow stops pip upgrading Airflow while adding the provider.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r requirements.txt
