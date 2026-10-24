//! Generated protobuf / gRPC types for Organism.
//! Produced by `build.rs` into `src/gen/` (`make proto` / `cargo build -p organism-proto`).

#![allow(clippy::all)]
#![allow(dead_code)]
#![allow(unused_imports)]

pub mod organism {
    pub mod v1 {
        // package organism.v1 — common.proto + contract.proto
        include!("gen/organism.v1.rs");

        pub mod calibration {
            include!("gen/organism.v1.calibration.rs");
        }
        pub mod exploration {
            include!("gen/organism.v1.exploration.rs");
        }
        pub mod registry {
            include!("gen/organism.v1.registry.rs");
        }
        pub mod router {
            include!("gen/organism.v1.router.rs");
        }
        pub mod rule {
            include!("gen/organism.v1.rule.rs");
        }
        pub mod trace {
            include!("gen/organism.v1.trace.rs");
        }
        pub mod workspace {
            include!("gen/organism.v1.workspace.rs");
        }
    }
}
