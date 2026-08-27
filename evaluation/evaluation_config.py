# Import Path to create operating-system-independent paths
from pathlib import Path

# Import the general Ragas metric type for type annotations
from ragas.metrics.base import Metric

# Import the three metrics used during evaluation
from ragas.metrics import (
    Faithfulness,
    ContextPrecision,
    ContextRecall,
)

# ============================================================
# RAGAS EVALUATION METRICS
# ============================================================

# Three metrics are now used:
#
# Faithfulness:
# Checks whether the generated answer is supported by the
# retrieved contexts.
#
# ContextPrecision:
# Checks whether the retrieved chunks are relevant and correctly
# ranked, with the most useful chunks appearing first.
#
# ContextRecall:
# Checks whether the retrieved contexts contain all information
# required by the ground-truth answer.
EVALUATION_METRICS: list[Metric] = [
    Faithfulness(),
    ContextPrecision(),
    ContextRecall(),
]


# ============================================================
# EVALUATION LLM CONFIGURATION
# ============================================================

# Model used by Ragas as a judge.
#
# This model does not answer the user's original question.
# It analyses the RAG answer, retrieved contexts and ground truth
# to calculate the evaluation scores.
EVALUATION_LLM_MODEL: str = "openai/gpt-oss-120b"


# ============================================================
# EVALUATION EMBEDDING CONFIGURATION
# ============================================================

# Embedding model available to Ragas during evaluation.
#
# We use the same lightweight model selected for the Treasoria
# baseline to avoid downloading the much larger BGE model
# during this first experiment.
EVALUATION_EMBEDDING_MODEL_NAME: str = (
    "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
)


# ============================================================
# EVALUATION PATHS
# ============================================================

# Absolute path to the evaluation/ directory
EVALUATION_ROOT_PATH: Path = Path(__file__).parent

# Directory where detailed and summary CSV results will be saved
EVALUATION_RESULTS_PATH: Path = (
    EVALUATION_ROOT_PATH / "evaluation_results"
)

# Directory containing vector stores created specifically
# for evaluation experiments
EXPERIMENTAL_VECTOR_STORES_PATH: Path = (
    EVALUATION_ROOT_PATH / "evaluation_vector_stores"
)

# Directory used to cache the evaluation embedding model
EVALUATION_EMBEDDING_CACHE_PATH: Path = (
    EVALUATION_ROOT_PATH / "evaluation_embedding_models"
)


# ============================================================
# API RATE-LIMIT CONFIGURATION
# ============================================================

# Pause between two Ragas evaluations.
#
# Ragas makes several internal LLM calls for each question.
# A 60-second pause allows the Groq token-per-minute window
# to recover before evaluating another question.
SLEEP_PER_EVALUATION: int = 60

# Optional pause between the generation of two chatbot answers.
#
# This is separate from the expensive Ragas evaluation stage.
SLEEP_PER_QUESTION: int = 6


# --- Configuration for Chunking Strategy Evaluation ---
CHUNKING_STRATEGY_CONFIGS: list[dict[str, int]] = [
    {"size": 250, "overlap": 50},   # Current baseline
    {"size": 512, "overlap": 50},
    {"size": 768, "overlap": 115},
    {"size": 1024, "overlap": 200},
]

# ============================================================
# RERANKER EVALUATION CONFIGURATION
# ============================================================

# Cross-encoder model used to rerank the chunks retrieved
# during the initial vector search
RERANKER_MODEL_NAME: str = (
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# retriever_k:
# Number of candidate chunks retrieved during the broad
# vector-search stage.
#
# reranker_n:
# Number of highest-ranked chunks retained after reranking
# and passed to the generator LLM.
RERANKER_CONFIGS: list[dict[str, int]] = [
    {"retriever_k": 10, "reranker_n": 2},
    {"retriever_k": 10, "reranker_n": 3},
    {"retriever_k": 20, "reranker_n": 3},
]

# ============================================================
# QUERY-REWRITING EVALUATION CONFIGURATION
# ============================================================

# Best reranker configuration selected during Stage 3.
#
# The vector retriever first selects 10 candidate chunks.
# The cross-encoder reranker then retains the best 2 chunks.
BEST_RERANKER_STRATEGY: dict[str, int] = {
    "retriever_k": 10,
    "reranker_n": 2,
}