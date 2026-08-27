# Import os to access environment variables
import os

# Import load_dotenv to read the GROQ_API_KEY from the .env file
from dotenv import load_dotenv

# Import the Groq integration used to initialise the evaluation LLM
from llama_index.llms.groq import Groq

# Import the Ragas Hugging Face embedding wrapper
from ragas.embeddings import HuggingFaceEmbeddings

# Import the wrapper that makes a LlamaIndex LLM compatible with Ragas
from ragas.llms.base import LlamaIndexLLMWrapper

# Import the evaluation-specific model names and cache path
from evaluation.evaluation_config import (
    EVALUATION_EMBEDDING_CACHE_PATH,
    EVALUATION_EMBEDDING_MODEL_NAME,
    EVALUATION_LLM_MODEL,
)


# Load the variables stored inside the project's .env file
#
# This makes GROQ_API_KEY available through os.getenv().
load_dotenv()


def initialise_evaluation_llm() -> Groq:
    """
    Initialise and return the Groq LLM used as the Ragas judge.

    This model is separate from the LLM used by the Treasoria
    chatbot. It evaluates the chatbot's generated answers.
    """

    # Retrieve the Groq API key from the environment
    api_key: str | None = os.getenv("GROQ_API_KEY")

    # Stop the application with a clear message if the key
    # cannot be found
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found. "
            "Make sure it is defined in the .env file."
        )

    # Create and return the independent evaluation model
    #
    # EVALUATION_LLM_MODEL currently contains:
    # moonshotai/kimi-k2-instruct
    return Groq(
        api_key=api_key,
        model=EVALUATION_LLM_MODEL,
    )


def load_ragas_models(
) -> tuple[LlamaIndexLLMWrapper, HuggingFaceEmbeddings]:
    """
    Load and return the LLM judge and embedding model
    required by Ragas.

    Returns
    -------
    tuple
        The first element is the wrapped evaluation LLM.
        The second element is the evaluation embedding model.
    """

    print("--- 🧠 Loading Ragas LLM and embeddings... ---")

    # Initialise Kimi K2 through the Groq API
    llm_for_evaluation: Groq = initialise_evaluation_llm()

    # Convert the LlamaIndex Groq object into a format
    # that the Ragas library can understand
    ragas_llm: LlamaIndexLLMWrapper = LlamaIndexLLMWrapper(
        llm=llm_for_evaluation,
    )

    # Ensure that the local directory for the evaluation
    # embedding model exists
    EVALUATION_EMBEDDING_CACHE_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Load the embedding model used by Ragas
    #
    # The model will be downloaded only if it is not already
    # available in this evaluation cache directory.
    ragas_embeddings: HuggingFaceEmbeddings = (
        HuggingFaceEmbeddings(
            model=EVALUATION_EMBEDDING_MODEL_NAME,
            cache_folder=(
                EVALUATION_EMBEDDING_CACHE_PATH.as_posix()
            ),
        )
    )

    # Return both components to the evaluation engine
    return ragas_llm, ragas_embeddings