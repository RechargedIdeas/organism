//! Binary Hypervector — A3.2 / D.1. DIM=10000 packed as [u64; 157].
use crate::errors::OrganismError;
use rand::Rng;

pub const DIM: usize = 10_000;
pub const WORD_COUNT: usize = 157;
pub const BYTES_LEN: usize = 1250;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Hypervector(pub [u64; WORD_COUNT]);

impl Hypervector {
    pub const DIM: usize = DIM;

    pub fn zeros() -> Self {
        Self([0u64; WORD_COUNT])
    }

    pub fn random<R: Rng + ?Sized>(rng: &mut R) -> Self {
        let mut words = [0u64; WORD_COUNT];
        for w in words.iter_mut() {
            *w = rng.gen();
        }
        let unused = WORD_COUNT * 64 - DIM;
        if unused > 0 {
            let mask = (1u64 << (64 - unused)) - 1;
            words[WORD_COUNT - 1] &= mask;
        }
        Self(words)
    }

    pub fn bind(&self, other: &Self) -> Self {
        let mut out = [0u64; WORD_COUNT];
        for i in 0..WORD_COUNT {
            out[i] = self.0[i] ^ other.0[i];
        }
        Self(out)
    }

    pub fn unbind(&self, role: &Self) -> Self {
        self.bind(role)
    }

    pub fn similarity(&self, other: &Self) -> f64 {
        let mut dist: u32 = 0;
        for i in 0..WORD_COUNT {
            dist += (self.0[i] ^ other.0[i]).count_ones();
        }
        1.0 - (dist as f64) / (DIM as f64)
    }

    /// Pack DIM bits as little-endian u64 words truncated to 1250 bytes.
    /// Name retains `_be` from A3.2; packing is LE-per-word so unused high
    /// bits of the last word are outside the truncated region (IMP-4).
    pub fn to_bytes_be(&self) -> [u8; BYTES_LEN] {
        let mut out = [0u8; BYTES_LEN];
        let mut idx = 0;
        for wi in 0..WORD_COUNT {
            let bytes = self.0[wi].to_le_bytes();
            for b in bytes {
                if idx >= BYTES_LEN {
                    break;
                }
                out[idx] = b;
                idx += 1;
            }
        }
        out
    }

    pub fn from_bytes_be(bytes: &[u8]) -> Result<Self, OrganismError> {
        if bytes.len() != BYTES_LEN {
            return Err(OrganismError::DimensionMismatch {
                expected: BYTES_LEN,
                actual: bytes.len(),
            });
        }
        let mut padded = [0u8; WORD_COUNT * 8];
        padded[..BYTES_LEN].copy_from_slice(bytes);
        let mut words = [0u64; WORD_COUNT];
        for i in 0..WORD_COUNT {
            let start = i * 8;
            let mut arr = [0u8; 8];
            arr.copy_from_slice(&padded[start..start + 8]);
            words[i] = u64::from_le_bytes(arr);
        }
        // Mask unused high bits of last word
        let unused = WORD_COUNT * 64 - DIM;
        if unused > 0 {
            let mask = (1u64 << (64 - unused)) - 1;
            words[WORD_COUNT - 1] &= mask;
        }
        Ok(Self(words))
    }

    pub fn bundle(hvs: &[Self]) -> Self {
        if hvs.is_empty() {
            return Self::zeros();
        }
        let n = hvs.len();
        let mut out = [0u64; WORD_COUNT];
        for wi in 0..WORD_COUNT {
            for bit in 0..64 {
                let ones = hvs.iter().filter(|hv| ((hv.0[wi] >> bit) & 1) == 1).count();
                if ones * 2 > n {
                    out[wi] |= 1u64 << bit;
                } else if ones * 2 == n {
                    let mut parity = 0u64;
                    for hv in hvs {
                        parity ^= (hv.0[wi] >> bit) & 1;
                    }
                    if parity == 1 {
                        out[wi] |= 1u64 << bit;
                    }
                }
            }
        }
        let unused = WORD_COUNT * 64 - DIM;
        if unused > 0 {
            let mask = (1u64 << (64 - unused)) - 1;
            out[WORD_COUNT - 1] &= mask;
        }
        Self(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand::rngs::StdRng;

    #[test]
    fn bind_unbind_exact() {
        let mut rng = StdRng::seed_from_u64(42);
        let a = Hypervector::random(&mut rng);
        let b = Hypervector::random(&mut rng);
        let bound = a.bind(&b);
        assert_eq!(bound.unbind(&a), b);
        assert_eq!(bound.unbind(&b), a);
        assert!((a.similarity(&a) - 1.0).abs() < 1e-9);
    }

    #[test]
    fn bytes_roundtrip() {
        let mut rng = StdRng::seed_from_u64(7);
        let hv = Hypervector::random(&mut rng);
        let raw = hv.to_bytes_be();
        assert_eq!(raw.len(), BYTES_LEN);
        let back = Hypervector::from_bytes_be(&raw).unwrap();
        assert_eq!(back, hv);
    }
}
