// Organism Kotlin SDK: pure Kotlin/JVM, no dependencies beyond the Kotlin stdlib, so Android (minSdk 24) and
// KotMoE's kotmoe-core can consume it. Behaviour is pinned to the Python reference by ../../conformance vectors.
plugins {
    kotlin("jvm")
    `maven-publish`
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

// The conformance vectors ship with the artifact as a separate classifier jar, so a consumer can check the exact
// version it pins against the behaviour it expects (docs/LIGHTSPEED_ON_ORGANISM.md, section 7.1).
val conformanceJar by tasks.registering(Jar::class) {
    archiveClassifier.set("conformance")
    from(rootProject.projectDir.resolve("../../conformance/vectors")) { into("vectors") }
}

// Private repository only. The default is a file repository under build/, so nothing leaves the machine. A shared
// repository is set in the user's Gradle properties (never in this file): organismPrivateRepo, organismRepoUser,
// organismRepoToken.
publishing {
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
            artifact(conformanceJar)
        }
    }
    repositories {
        maven {
            name = "private"
            url = uri(providers.gradleProperty("organismPrivateRepo").getOrElse(file("build/private-repo").toURI().toString()))
            val user = providers.gradleProperty("organismRepoUser")
            val token = providers.gradleProperty("organismRepoToken")
            if (user.isPresent && token.isPresent) {
                credentials {
                    username = user.get()
                    password = token.get()
                }
            }
        }
    }
}
