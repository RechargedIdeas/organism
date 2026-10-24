fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../proto");
    let protos = [
        "organism/v1/common.proto",
        "organism/v1/contract.proto",
        "organism/v1/registry.proto",
        "organism/v1/router.proto",
        "organism/v1/workspace.proto",
        "organism/v1/trace.proto",
        "organism/v1/exploration.proto",
        "organism/v1/rule.proto",
        "organism/v1/calibration.proto",
    ];
    let outs: Vec<_> = protos
        .iter()
        .map(|p| proto_root.join(p))
        .collect();
    // Ensure OUT_DIR-style gen path used by Makefile exists alongside include!.
    let gen = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/gen");
    std::fs::create_dir_all(&gen)?;
    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .out_dir(&gen)
        .compile(&outs, &[&proto_root])?;
    println!("cargo:rerun-if-changed={}", proto_root.display());
    Ok(())
}
