pluginManagement {
    plugins {
        // Same Kotlin version as KotMoE so the SDK can be included in its build unchanged.
        id("org.jetbrains.kotlin.jvm") version "1.9.22"
    }
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "organism-kotlin"
