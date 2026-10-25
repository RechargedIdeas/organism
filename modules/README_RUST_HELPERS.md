# Rust helper crates vs Python modules

`modules/hdc` and `modules/kernel` are **tiny Rust helper crates**
(`organism-hdc`, `organism-kernel`) used by the Cargo workspace for bind/RBF
helpers. They are **not** the Python substrate modules.

Python modules live in:
- `modules/hdc_module/` — HDC substrate (primary)
- `modules/kernel_module/` — kernel RBF substrate (primary)

Do not import from `modules/hdc` / `modules/kernel` as Python packages.
See workspace `Cargo.toml` members list.
