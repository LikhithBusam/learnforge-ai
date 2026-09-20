# Hybrid Retrieval & Reciprocal Rank Fusion (Phase 4)

## 1. Dual-Path Retrieval

Hybrid retrieval combines dense semantic retrieval with sparse lexical retrieval:

1. **Vector Retrieval (Dense Semantic):**
   - Query embedded via AI Gateway (`model_role="embedding"`).
   - Searched against table `chunk_embeddings` using pgvector cosine distance (`<=>`).
   - Scored as $\text{vector\_score} = \max(0, 1 - \text{distance})$.
   - Filtered by `(project_id, owner_id)`.

2. **PostgreSQL Full-Text Search (Sparse Lexical):**
   - Searched against `chunks.content_tsv` using PostgreSQL text search.
   - Query words combined with `to_tsquery('english', 'term1 | term2 ...')` or `plainto_tsquery`.
   - Scored with `ts_rank_cd` cover-density ranking.
   - Filtered by `(project_id, owner_id)`.

---

## 2. Reciprocal Rank Fusion (RRF)

Candidates from both lists are combined using Reciprocal Rank Fusion:

$$RRF(d) = \sum_{m \in \{\text{vector}, \text{lexical}\}} \frac{1}{k + \text{rank}_m(d)}$$

Where:
- $k = 60$ (standard information retrieval smoothing constant).
- $\text{rank}_m(d)$ is the 1-indexed rank of candidate $d$ in retrieval list $m$.
- Candidates appearing in both dense and sparse lists receive additive scores, boosting them above single-list hits.
