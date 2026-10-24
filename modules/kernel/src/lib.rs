//! organism-kernel — RBF similarity helper (v1.0-F; Python remains primary).
pub fn rbf(a: &[f64], b: &[f64], gamma: f64) -> f64 {
    let n = a.len().min(b.len());
    let mut s = 0.0;
    for i in 0..n {
        let d = a[i] - b[i];
        s += d * d;
    }
    (-gamma * s).exp()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn identical_is_one() {
        let v = [1.0, 2.0, 3.0];
        assert!((rbf(&v, &v, 1.0) - 1.0).abs() < 1e-12);
    }
}
