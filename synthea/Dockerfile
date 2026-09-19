# Stage 1: build Synthea from a pinned commit.
#
# The dev-tier dataset was generated with Synthea's rolling
# master-branch-latest release, since overwritten, so the jar cannot be
# re-downloaded. A commit hash is permanent; building from it is the only way
# to reproduce docs/calibration.md on another machine. See decision.md D35.
FROM eclipse-temurin:17-jdk AS build

ARG SYNTHEA_COMMIT=7e08387c68a7f0e21d13076609a159fd473fc902

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
# Fetch only the pinned commit. A full clone pulls the whole history for no use.
RUN git init -q . \
 && git remote add origin https://github.com/synthetichealth/synthea.git \
 && git fetch -q --depth 1 origin "${SYNTHEA_COMMIT}" \
 && git checkout -q FETCH_HEAD

# build.gradle stamps Build-Version from version.txt before its own task writes
# that file, so a fresh build says "N/A". Write it first, the way Synthea does.
RUN git describe --tags --always > src/main/resources/version.txt \
 && ./gradlew uberJar --no-daemon \
 && cp build/libs/synthea-with-dependencies.jar /synthea.jar

# Stage 2: runtime only. Java 21 because the recorded run used Temurin 21.
FROM eclipse-temurin:21-jre

COPY --from=build /synthea.jar /app/synthea.jar
COPY synthea.properties /app/synthea.properties

WORKDIR /data

# Seeds, reference date and end date are the recorded dev tier. Without -e,
# Synthea simulates up to the day it runs, so the same seeds give a different
# dataset every day (errors.md E31). 20260808 is when the recorded run was made.
# America/Chicago: the recorded run was made on a laptop in US Central time, and
# Synthea turns timestamps into dates in the JVM's zone. Under the container's
# default UTC, a quarter of patients came out different (decision.md D35).
# -Xmx3g: Java defaults to a quarter of the memory it sees, ~1 GB inside Docker
# Desktop's 4 GB VM. At 1 GB patients die of OutOfMemoryError mid-generation and
# are silently dropped, with exit code 0 (errors.md E30).
ENTRYPOINT ["java", "-Duser.timezone=America/Chicago", "-Xmx3g", \
            "-jar", "/app/synthea.jar", \
            "-c", "/app/synthea.properties", \
            "-p", "1000", "-s", "12345", "-cs", "12345", "-r", "20260101", \
            "-e", "20260808", \
            "Massachusetts"]
