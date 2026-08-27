# Import datetime to add timestamps to saved result files
from datetime import datetime

# Import Path to manage file and folder paths
from pathlib import Path

# Import time to pause execution between API calls
import time

# Import Any for values whose exact type can vary
from typing import Any

# Import the Hugging Face Dataset structure required by Ragas
from datasets import Dataset

# Import the main LlamaIndex components used to:
# - represent documents;
# - load files;
# - build vector indexes;
# - save and reload indexes.
from llama_index.core import (
    Document,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)

# Import the base type representing a LlamaIndex query engine
from llama_index.core.query_engine import BaseQueryEngine

# Import the text splitter used to create overlapping chunks
from llama_index.core.node_parser import SentenceSplitter

# Import the Hugging Face embedding model used by the RAG system
from llama_index.embeddings.huggingface import (
    HuggingFaceEmbedding,
)

# Import pandas to create, combine and save result tables
import pandas as pd

# Import the main Ragas evaluation function
from ragas import evaluate

# Import the possible result types returned by Ragas
from ragas.dataset_schema import EvaluationResult
from ragas.executor import Executor

# Import the Ragas embedding wrapper type
from ragas.embeddings import HuggingFaceEmbeddings

# Import the wrapper type used for the evaluation LLM
from ragas.llms.base import LlamaIndexLLMWrapper

# Import RunConfig to control parallelism, retries and waiting
from ragas.run_config import RunConfig

# Import evaluation settings
from evaluation.evaluation_config import (
    EVALUATION_METRICS,
    EVALUATION_RESULTS_PATH,
    EXPERIMENTAL_VECTOR_STORES_PATH,
    SLEEP_PER_EVALUATION,
    SLEEP_PER_QUESTION,
)

# Import our Treasoria questions and ground-truth answers
from evaluation.evaluation_questions import EVALUATION_DATA

# Import the path containing the Treasoria source documents
from src.config import DATA_PATH


def get_evaluation_data() -> tuple[list[str], list[str]]:
    """
    Extract questions and ground-truth answers from EVALUATION_DATA.

    Returns
    -------
    tuple[list[str], list[str]]
        The first list contains the evaluation questions.
        The second list contains the corresponding ideal answers.
    """

    # Extract every value stored under the "question" key
    questions: list[str] = [
        item["question"]
        for item in EVALUATION_DATA
    ]

    # Extract every value stored under the "ground_truth" key
    ground_truths: list[str] = [
        item["ground_truth"]
        for item in EVALUATION_DATA
    ]

    # Return both lists in the same order
    #
    # This order is important because questions[0] must correspond
    # to ground_truths[0], questions[1] to ground_truths[1], etc.
    return questions, ground_truths


def get_or_build_index(
    chunk_size: int,
    chunk_overlap: int,
    embed_model: HuggingFaceEmbedding,
) -> VectorStoreIndex:
    """
    Load an existing experimental vector store if available.

    If no vector store exists for the requested chunk configuration,
    build a new index from the Treasoria documents, save it and return it.
    """

    # Create a unique name for the experiment using its
    # chunk size and chunk overlap
    #
    # Example:
    # vs_chunk_250_overlap_50
    vector_store_id: str = (
        f"vs_chunk_{chunk_size}_overlap_{chunk_overlap}"
    )

    # Build the complete path where this experimental vector
    # store will be saved
    #
    # Example:
    # evaluation/evaluation_vector_stores/
    # vs_chunk_250_overlap_50/
    specific_vector_store_path: Path = (
        EXPERIMENTAL_VECTOR_STORES_PATH
        / vector_store_id
    )

    # Check whether a vector store for this experiment
    # has already been created
    if specific_vector_store_path.exists():

        # Avoid rebuilding the same index on every evaluation
        print(
            f"--- Loading existing index from: "
            f"{vector_store_id} ---"
        )

        # Connect LlamaIndex to the saved vector-store directory
        storage_context: StorageContext = (
            StorageContext.from_defaults(
                persist_dir=str(specific_vector_store_path),
            )
        )

        # Load the saved index using the same embedding model
        # that was used when the index was originally created
        index: VectorStoreIndex = load_index_from_storage(
            storage_context,
            embed_model=embed_model,
        )

    else:
        # No saved index exists for this chunk configuration
        print(
            f"--- Creating new index for: "
            f"{vector_store_id} ---"
        )

        # Load all supported documents from the project's data/
        # directory
        documents: list[Document] = (
            SimpleDirectoryReader(
                input_dir=DATA_PATH,
            ).load_data()
        )

        # Stop with a clear error if the data/ directory
        # contains no readable document
        if not documents:
            raise ValueError(
                f"No documents found in {DATA_PATH}. "
                "Cannot build the evaluation index."
            )

        # Divide the documents into overlapping chunks
        text_splitter: SentenceSplitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # Create the vector index:
        #
        # 1. Split documents into chunks
        # 2. Convert each chunk into an embedding
        # 3. Store the vectors and original text
        index: VectorStoreIndex = (
            VectorStoreIndex.from_documents(
                documents,
                transformations=[text_splitter],
                embed_model=embed_model,
            )
        )

        # Save the experimental vector store for future evaluations
        index.storage_context.persist(
            persist_dir=str(specific_vector_store_path),
        )

        print(
            f"--- Saved new index to: "
            f"{vector_store_id} ---"
        )

    # Return either the loaded or newly created index
    return index


def generate_qa_dataset(
    query_engine: BaseQueryEngine,
    questions: list[str],
    ground_truths: list[str],
) -> Dataset:
    """
    Generate RAG answers and retrieve their source contexts.

    The questions, generated answers, retrieved contexts and
    ground-truth answers are combined into a Hugging Face Dataset
    that can later be evaluated by Ragas.
    """

    # Ensure that every question has a corresponding ground truth
    if len(questions) != len(ground_truths):
        raise ValueError(
            "The number of questions must match the number "
            "of ground-truth answers."
        )

    # Store the answers generated by the Treasoria RAG system
    responses: list[str] = []

    # Store the chunks retrieved for every question
    #
    # It is a list of lists because each question can retrieve
    # several chunks. With similarity_top_k=2, each inner list
    # should normally contain two contexts.
    contexts: list[list[str]] = []

    # Process each evaluation question one at a time
    for question_index, question in enumerate(questions):

        print(
            "Fetching context and synthesising response for question "
            f"{question_index + 1}/{len(questions)}: "
            f"'{question[:50]}...'"
        )

        # Send ONLY the actual question to the query engine
        #
        # Important:
        # Do not concatenate the system prompt with the question.
        # Otherwise, the system-prompt text would become part of
        # the query embedding and could distort semantic retrieval.
        response_object = query_engine.query(question)

        # Convert the generated response object into plain text
        responses.append(str(response_object))

        # Extract the original text of every retrieved source node
        #
        # These contexts will later be used by Ragas to evaluate:
        # - whether the answer is faithful;
        # - whether all necessary information was retrieved.
        retrieved_contexts: list[str] = [
            node.get_content()
            for node in response_object.source_nodes
        ]

        contexts.append(retrieved_contexts)

        # Pause between question-generation API calls when several
        # questions are active.
        #
        # No pause is necessary after the final question.
        if question_index + 1 < len(questions):
            print(
                f"Taking a {SLEEP_PER_QUESTION}-second breather "
                "before generating the next answer."
            )

            time.sleep(SLEEP_PER_QUESTION)

    # Build the exact column structure expected by the legacy
    # Ragas evaluate() function used in the course notebook
    response_data: dict[str, list[Any]] = {
        "question": questions,
        "answer": responses,
        "contexts": contexts,
        "ground_truth": ground_truths,
    }

    # Convert the Python dictionary into a Hugging Face Dataset
    return Dataset.from_dict(response_data)



def evaluate_with_rate_limit(
    qa_dataset: Dataset,
    ragas_llm: LlamaIndexLLMWrapper,
    ragas_embeddings: HuggingFaceEmbeddings,
) -> pd.DataFrame:
    """
    Evaluate the RAG dataset one question at a time.

    The function limits parallel calls and pauses between questions
    to reduce the risk of exceeding Groq API rate limits.
    """

    print("--- 🐢 Running evaluation with rate limiting... ---")

    # Count the total number of questions to evaluate
    number_of_questions: int = len(qa_dataset)

    # Stop with a clear error if the dataset is empty
    if number_of_questions == 0:
        raise ValueError(
            "The evaluation dataset is empty. "
            "Add at least one question before running evaluation."
        )

    # Configure how Ragas sends requests to the judge model
    #
    # max_workers=1:
    # Run only one evaluation task at a time.
    #
    # max_retries=2:
    # Retry a failed request at most twice.
    # We deliberately avoid max_retries=10 because repeated
    # requests can consume the remaining token allowance.
    #
    # max_wait=60:
    # Allow Ragas to wait up to 60 seconds before retrying.
    run_config: RunConfig = RunConfig(
        max_workers=1,
        max_retries=2,
        max_wait=60,
    )

    # Store the evaluation result for each individual question
    partial_results_list: list[pd.DataFrame] = []

    # Evaluate every dataset row separately
    for question_index, row in enumerate(qa_dataset):

        print(
            f"Evaluating response for question "
            f"{question_index + 1}/{number_of_questions}: "
            f"'{row['question'][:50]}...'"
        )

        # Ragas expects a Dataset, even when evaluating
        # only one question.
        #
        # Convert the current row back into a one-row Dataset.
        single_row_dataset: Dataset = Dataset.from_dict(
            {
                key: [value]
                for key, value in row.items()
            }
        )

        # Run Ragas on this single question
        #
       # EVALUATION_METRICS currently contains:
# - Faithfulness()
# - ContextPrecision()
# - ContextRecall()
        result: EvaluationResult | Executor = evaluate(
            dataset=single_row_dataset,
            metrics=EVALUATION_METRICS,
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=run_config,
            raise_exceptions=False,
        )

        # Convert the result into a pandas DataFrame
        question_results_df: pd.DataFrame = result.to_pandas()

        # Save this question's result in the list
        partial_results_list.append(
            question_results_df
        )

        # Pause for approximately one Groq rate-limit window
        # before evaluating the next question.
        #
        # Do not pause after the final question.
        if question_index + 1 < number_of_questions:
            print(
                f"Taking a {SLEEP_PER_EVALUATION}-second "
                "breather to respect the API rate limit."
            )

            time.sleep(SLEEP_PER_EVALUATION)

    # Combine the separate question results into one table
    results_df: pd.DataFrame = pd.concat(
        partial_results_list,
        ignore_index=True,
    )

    print("--- ✅ Evaluation complete! ---")

    # Return the complete evaluation table
    return results_df



def save_results(
    results_df: pd.DataFrame,
    filename_prefix: str,
) -> None:
    """
    Save detailed evaluation results and average metric scores
    into timestamped CSV files.
    """

    # Use the evaluation_results/ directory defined
    # inside evaluation_config.py
    results_dir: Path = EVALUATION_RESULTS_PATH

    # Create the result directory if it does not exist
    #
    # parents=True creates missing parent folders.
    # exist_ok=True avoids an error if the folder already exists.
    results_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Create a timestamp so that each experiment receives
    # a unique filename and previous results are not overwritten
    timestamp: str = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    # ========================================================
    # SAVE DETAILED RESULTS
    # ========================================================

    # Create the path for the question-level result file
    detailed_path: Path = (
        results_dir
        / f"{filename_prefix}_detailed_{timestamp}.csv"
    )

    # Save every question, answer, context, ground truth
    # and metric score
    results_df.to_csv(
        detailed_path,
        index=False,
    )

    print(
        f"--- 💾 Detailed results saved to "
        f"{detailed_path} ---"
    )

    # ========================================================
    # CREATE AND SAVE THE SUMMARY
    # ========================================================

    # Create the path for the average-score summary
    summary_path: Path = (
        results_dir
        / f"{filename_prefix}_summary_{timestamp}.csv"
    )

    # Detect experiment parameters that may have been added
    # to the DataFrame
    #
    # Only columns that actually exist will be selected.
    parameter_columns: list[str] = [
        column
        for column in [
            "chunk_size",
            "chunk_overlap",
            "retriever_k",
            "reranker_n",
            "use_hyde",
        ]
        if column in results_df.columns
    ]

    # If experiment-configuration columns exist, calculate
    # average numeric scores for each configuration
    if parameter_columns:
        summary_df: pd.DataFrame = (
            results_df
            .groupby(parameter_columns)
            .mean(numeric_only=True)
            .reset_index()
        )

    else:
        # If no experiment parameters exist, calculate one
        # overall average for every numeric metric column
        summary_df = pd.DataFrame(
            [
                results_df.mean(
                    numeric_only=True
                )
            ]
        )

    # Save the summary table
    summary_df.to_csv(
        summary_path,
        index=False,
    )

    print(
        f"--- 💾 Summary results saved to "
        f"{summary_path} ---"
    )