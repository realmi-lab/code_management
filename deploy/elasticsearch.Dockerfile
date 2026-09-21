ARG ES_IMAGE=docker.elastic.co/elasticsearch/elasticsearch:8.17.0
FROM ${ES_IMAGE}
RUN bin/elasticsearch-plugin install --batch analysis-nori
