//! organism-hdc — tiny binary HV bind/bundle helpers (v1.0-F).
pub fn bind_xor(a: &[u64], b: &[u64]) -> Vec<u64> {
    a.iter().zip(b.iter()).map(|(x, y)| x ^ y).collect()
}

pub fn hamming_similarity(a: &[u64], b: &[u64], bits: usize) -> f64 {
    let mut diff = 0u32;
    let n = a.len().min(b.len());
    for i in 0..n {
        diff += (a[i] ^ b[i]).count_ones();
    }
    let bits = bits.max(1) as f64;
    1.0 - (diff as f64 / bits)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn xor_involution() {
        let a = vec![0xABCDu64, 1];
        let b = vec![0x1234u64, 2];
        let c = bind_xor(&a, &b);
        assert_eq!(bind_xor(&c, &b), a);
    }
}
