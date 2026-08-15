FROM ghcr.io/cirruslabs/android-sdk:36

USER root
WORKDIR /workspace

COPY . .
RUN chmod +x gradlew

ARG STUDY_BUDDY_API_URL=http://10.0.2.2:8010
ENV STUDY_BUDDY_API_URL=$STUDY_BUDDY_API_URL

CMD ["sh", "-c", "./gradlew --no-daemon assembleDebug -PSTUDY_BUDDY_API_URL=\"$STUDY_BUDDY_API_URL\" && mkdir -p /output && cp app/build/outputs/apk/debug/app-debug.apk /output/study-buddy-debug.apk"]
