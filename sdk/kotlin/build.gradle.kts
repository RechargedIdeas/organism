// Organism Kotlin SDK: pure Kotlin/JVM, no dependencies beyond the Kotlin stdlib, so Android (minSdk 24) and
// KotMoE's kotmoe-core can consume it. Behaviour is pinned to the Python reference by ../../conformance vectors.
plugins {
    kotlin("jvm")
}

group = "org.organism"
version = "1.11.0-dev"

repositories {
    mavenCentral()
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}

tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
    kotlinOptions.jvmTarget = "11"
}

dependencies {
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
    // Conformance vectors live at the repo root so every language reads the same files.
    systemProperty("organism.conformance.dir", rootProject.projectDir.resolve("../../conformance/vectors").canonicalPath)
}
