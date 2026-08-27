# Import Path to create file and folder paths that work
# correctly on macOS, Windows and Linux
from pathlib import Path


# ============================================================
# LLM MODEL CONFIGURATION
# ============================================================

# Name of the Large Language Model used to generate responses
LLM_MODEL: str = "openai/gpt-oss-20b"

# Maximum number of new tokens the LLM can generate
LLM_MAX_NEW_TOKENS: int = 1200

# Controls randomness:
# a low value produces stable and predictable responses
LLM_TEMPERATURE: float = 0.09

# Controls the range of probable tokens considered
# 0.9 allows some variety while remaining coherent
LLM_TOP_P: float = 0.9

# Reduces unnecessary repetitions in generated responses
# 1.0 means no penalty; 1.03 applies a small penalty
LLM_REPETITION_PENALTY: float = 1.03

# Controls the amount of internal reasoning used by GPT-OSS.
# "low" reduces latency and token consumption for factual RAG answers.
LLM_REASONING_EFFORT: str = "low"

# ============================================================
# SYSTEM PROMPT CONFIGURATION
# ============================================================

# Defines the chatbot's role, behaviour and constraints
LLM_SYSTEM_PROMPT: str = (
    "You are Treasoria, a professional AI financial assistant for SMEs. "
    "Answer using only information supported by the retrieved Treasoria "
    "documents. Never invent financial figures, scripts, tests or company "
    "data. If the documents do not support a claim, say that the information "
    "is unavailable. Explain financial concepts clearly and practically. "
    "Keep answers under 300 words unless the user explicitly asks for more "
    "detail. Ask for clarification when the question is ambiguous."
)


# ============================================================
# EMBEDDING MODEL CONFIGURATION
# ============================================================

# Embedding model used to convert text chunks into numerical vectors
# This is different from the LLM that generates the final answers
EMBEDDING_MODEL_NAME: str = (
    "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
)


# ============================================================
# RAG AND VECTOR STORE CONFIGURATION
# ============================================================

# Number of the most relevant chunks retrieved from the vector store
# For every question, the system will retrieve the two closest chunks
# Number of candidate chunks retrieved before reranking
SIMILARITY_TOP_K: int = 10

# Maximum size of each document chunk in tokens
CHUNK_SIZE: int = 1024

# Number of tokens shared between two adjacent chunks
# This helps prevent important information from being split
CHUNK_OVERLAP: int = 200

# ============================================================
# RERANKER CONFIGURATION
# ============================================================

# Number of chunks retained after reranking
RERANKER_TOP_N: int = 2

# Cross-encoder selected during the Treasoria evaluation
RERANKER_MODEL_NAME: str = (
    "cross-encoder/ms-marco-MiniLM-L6-v2"
)

# ============================================================
# CHAT MEMORY CONFIGURATION
# ============================================================

# Maximum size of the detailed conversational history
# Older messages can be summarised when this limit is reached
CHAT_MEMORY_TOKEN_LIMIT: int = 1200


# ============================================================
# PROJECT AND STORAGE PATHS
# ============================================================

# config.py is located inside src/
# The first parent is src/ and the second parent is RAG_PROJECT/
# Therefore, ROOT_PATH represents the project's root directory
ROOT_PATH: Path = Path(__file__).parent.parent

# Directory containing the source documents
# This points to RAG_PROJECT/data/
DATA_PATH: Path = ROOT_PATH / "data"

# Directory where the embedding model will be cached locally
# This points to:
# RAG_PROJECT/local_storage/embedding_model/
EMBEDDING_CACHE_PATH: Path = (
    ROOT_PATH / "local_storage" / "embedding_model"
)

# Directory where the vector index will be stored
# This points to:
# RAG_PROJECT/local_storage/vector_store/
# Use a separate vector store for every chunking configuration
VECTOR_STORE_PATH: Path = (
    ROOT_PATH
    / "local_storage"
    / f"vector_store_chunk_{CHUNK_SIZE}_overlap_{CHUNK_OVERLAP}"
)