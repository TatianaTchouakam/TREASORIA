# Import os to read environment variables
import os

# Import load_dotenv to load variables from the .env file
from dotenv import load_dotenv

# Import the Hugging Face embedding integration from LlamaIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# Import the Groq LLM integration from LlamaIndex
from llama_index.llms.groq import Groq

# Import the required parameters from config.py
from src.config import (
    EMBEDDING_CACHE_PATH,
    EMBEDDING_MODEL_NAME,
    LLM_MAX_NEW_TOKENS,
    LLM_MODEL,
    LLM_REASONING_EFFORT,
    LLM_TEMPERATURE,
)


# Load the environment variables stored in the .env file
# This makes GROQ_API_KEY available to Python
load_dotenv()


def initialise_llm() -> Groq:
    """Initialise and return the Groq language model."""

    # Read the Groq API key from the environment
    api_key: str | None = os.getenv("GROQ_API_KEY")

    # Stop the program with a clear message if the key is missing
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found. "
            "Make sure it is defined in your .env file."
        )

    # Create and return the Groq LLM
    # This model will generate the chatbot's final responses
    return Groq(
    api_key=api_key,
    model=LLM_MODEL,
    max_tokens=LLM_MAX_NEW_TOKENS,
    temperature=LLM_TEMPERATURE,
    additional_kwargs={
        "reasoning_effort": LLM_REASONING_EFFORT,
    },
)


def get_embedding_model() -> HuggingFaceEmbedding:
    """Initialise and return the Hugging Face embedding model."""

    # Create the embedding model cache directory
    # parents=True creates local_storage if it does not exist
    # exist_ok=True prevents an error if the folder already exists
    EMBEDDING_CACHE_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Load and return the embedding model
    # It will transform document chunks and questions into vectors
    return HuggingFaceEmbedding(
        model_name=EMBEDDING_MODEL_NAME,

        # Convert the Path object into a string path
        # understood by the Hugging Face integration
        cache_folder=EMBEDDING_CACHE_PATH.as_posix(),
    )