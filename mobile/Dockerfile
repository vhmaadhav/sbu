FROM ghcr.io/cirruslabs/android-sdk:36

USER root
WORKDIR /workspace

COPY . .
RUN chmod +x gradlew

ARG AXIOM_TRACE_API_URL=http://10.0.2.2:8010
ENV AXIOM_TRACE_API_URL=$AXIOM_TRACE_API_URL

CMD ["sh", "-c", "./gradlew --no-daemon assembleDebug -PAXIOM_TRACE_API_URL=\"$AXIOM_TRACE_API_URL\" && mkdir -p /output && cp app/build/outputs/apk/debug/app-debug.apk /output/axiom-trace-debug.apk"]
