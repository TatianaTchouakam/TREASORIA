# Import the Hugging Face Dataset used for the QA dataset
from datasets import Dataset

# Import the vector-index type used by the RAG system
from llama_index.core.indices import VectorStoreIndex

# Import the query-engine types
from llama_index.core.query_engine import (
    BaseQueryEngine,
    RetrieverQueryEngine,
    TransformQueryEngine,
)

from llama_index.core.indices.query.query_transform import (
    HyDEQueryTransform,
)

# Import the cross-encoder reranker
from llama_index.core.postprocessor import (
    SentenceTransformerRerank,
)

# Import the Hugging Face embedding type used by LlamaIndex
from llama_index.embeddings.huggingface import (
    HuggingFaceEmbedding,
)

# Import the Groq LLM type
from llama_index.llms.groq import Groq

# Import pandas for evaluation results
import pandas as pd

# Import the Ragas embedding-wrapper type
from ragas.embeddings import HuggingFaceEmbeddings

# Import the Ragas-compatible LLM-wrapper type
from ragas.llms.base import LlamaIndexLLMWrapper

# Import the evaluation experiment configurations
from evaluation.evaluation_config import (
    BEST_RERANKER_STRATEGY,
    CHUNKING_STRATEGY_CONFIGS,
    RERANKER_CONFIGS,
    RERANKER_MODEL_NAME,
)

# Import evaluation helper functions
from evaluation.evaluation_helper_functions import (
    evaluate_with_rate_limit,
    generate_qa_dataset,
    get_evaluation_data,
    get_or_build_index,
    save_results,
)

# Import the independent Ragas judge loader
from evaluation.evaluation_model_loader import (
    load_ragas_models,
)

# Import the selected RAG parameters
from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    SIMILARITY_TOP_K,
)

# Import the product models being evaluated
from src.model_loader import (
    get_embedding_model,
    initialise_llm,
)


# ============================================================
# STAGE 1: BASELINE EVALUATION
# ============================================================

def evaluate_baseline() -> None:
    """
    Evaluate the current Treasoria RAG configuration.

    The function uses the chunking and retrieval parameters
    currently defined in src/config.py.
    """

    print(
        "--- 🚀 Stage 1: Evaluating Treasoria "
        "baseline configuration ---"
    )

    # Load the LLM used to generate Treasoria responses
    llm_to_test: Groq = initialise_llm()

    # Load the embedding model used for retrieval
    embed_model_to_test: HuggingFaceEmbedding = (
        get_embedding_model()
    )

    # Load evaluation questions and reference answers
    questions: list[str]
    ground_truths: list[str]

    questions, ground_truths = get_evaluation_data()

    print(
        f"--- Loaded {len(questions)} evaluation "
        "question(s) ---"
    )

    # Create or load the vector index
    index: VectorStoreIndex = get_or_build_index(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        embed_model=embed_model_to_test,
    )

    # Create the standard query engine without reranking
    query_engine: BaseQueryEngine = index.as_query_engine(
        similarity_top_k=SIMILARITY_TOP_K,
        llm=llm_to_test,
    )

    # Generate answers and collect retrieved contexts
    qa_dataset: Dataset = generate_qa_dataset(
        query_engine=query_engine,
        questions=questions,
        ground_truths=ground_truths,
    )

    print(
        "--- Loading the independent Ragas judge "
        "for baseline evaluation... ---"
    )

    # Load the independent Ragas judge and embeddings
    ragas_llm: LlamaIndexLLMWrapper
    ragas_embeddings: HuggingFaceEmbeddings

    ragas_llm, ragas_embeddings = load_ragas_models()

    print(
        "--- Running Ragas evaluation for "
        "the baseline... ---"
    )

    # Run the evaluation with rate-limit protection
    results_df: pd.DataFrame = evaluate_with_rate_limit(
        qa_dataset=qa_dataset,
        ragas_llm=ragas_llm,
        ragas_embeddings=ragas_embeddings,
    )

    # Record the baseline parameters
    results_df["chunk_size"] = CHUNK_SIZE
    results_df["chunk_overlap"] = CHUNK_OVERLAP
    results_df["retriever_k"] = SIMILARITY_TOP_K

    # Save detailed and summary results
    save_results(
        results_df=results_df,
        filename_prefix="baseline_evaluation",
    )

    print(
        "--- ✅ Treasoria Baseline Evaluation "
        "Complete ---"
    )


# ============================================================
# STAGE 2: CHUNKING STRATEGY EVALUATION
# ============================================================

def evaluate_chunking_strategies() -> None:
    """
    Evaluate several chunk-size and chunk-overlap configurations.

    All other RAG parameters remain unchanged so that the effect
    of chunking can be compared fairly.
    """

    print(
        "--- 🚀 Stage 2: Evaluating Treasoria "
        "chunking strategies ---"
    )

    # Load the same LLM for every experiment
    llm_to_test: Groq = initialise_llm()

    # Load the same embedding model for every experiment
    embed_model_to_test: HuggingFaceEmbedding = (
        get_embedding_model()
    )

    # Load evaluation questions and ground truths
    questions: list[str]
    ground_truths: list[str]

    questions, ground_truths = get_evaluation_data()

    print(
        f"--- Loaded {len(questions)} evaluation "
        "question(s) ---"
    )

    # Load the independent Ragas judge
    ragas_llm: LlamaIndexLLMWrapper
    ragas_embeddings: HuggingFaceEmbeddings

    ragas_llm, ragas_embeddings = load_ragas_models()

    # Store results from all chunking configurations
    all_results: list[pd.DataFrame] = []

    # Test every chunking configuration
    for config in CHUNKING_STRATEGY_CONFIGS:

        chunk_size: int = config["size"]
        chunk_overlap: int = config["overlap"]

        print(
            "\n--- Testing chunk configuration: "
            f"size={chunk_size}, "
            f"overlap={chunk_overlap} ---"
        )

        # Create or load the index for this configuration
        index: VectorStoreIndex = get_or_build_index(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embed_model=embed_model_to_test,
        )

        # Create the standard query engine
        query_engine: BaseQueryEngine = index.as_query_engine(
            similarity_top_k=SIMILARITY_TOP_K,
            llm=llm_to_test,
        )

        # Generate answers and retrieve contexts
        qa_dataset: Dataset = generate_qa_dataset(
            query_engine=query_engine,
            questions=questions,
            ground_truths=ground_truths,
        )

        print(
            "--- Running Ragas evaluation for "
            f"chunk_size={chunk_size}, "
            f"chunk_overlap={chunk_overlap} ---"
        )

        # Evaluate this chunking configuration
        results_df: pd.DataFrame = evaluate_with_rate_limit(
            qa_dataset=qa_dataset,
            ragas_llm=ragas_llm,
            ragas_embeddings=ragas_embeddings,
        )

        # Record the tested parameters
        results_df["chunk_size"] = chunk_size
        results_df["chunk_overlap"] = chunk_overlap
        results_df["retriever_k"] = SIMILARITY_TOP_K

        all_results.append(results_df)

    # Combine all chunking results
    final_df: pd.DataFrame = pd.concat(
        all_results,
        ignore_index=True,
    )

    # Save detailed and summary results
    save_results(
        results_df=final_df,
        filename_prefix="chunking_evaluation",
    )

    print(
        "--- ✅ Treasoria Chunking Strategy "
        "Evaluation Complete ---"
    )


# ============================================================
# STAGE 3: RERANKER STRATEGY EVALUATION
# ============================================================

def evaluate_reranker_strategies() -> None:
    """
    Evaluate different reranker configurations using the
    preliminary optimal chunking strategy from src/config.py.
    """

    print(
        "--- 🚀 Stage 3: Evaluating Treasoria "
        "reranker strategies ---"
    )

    # Load the LLM used to generate Treasoria responses
    llm_to_test: Groq = initialise_llm()

    # Load the embedding model used for retrieval
    embed_model_to_test: HuggingFaceEmbedding = (
        get_embedding_model()
    )

    # Load evaluation questions and ground truths
    questions: list[str]
    ground_truths: list[str]

    questions, ground_truths = get_evaluation_data()

    print(
        f"--- Loaded {len(questions)} evaluation "
        "question(s) ---"
    )

    # Load the independent Ragas judge
    ragas_llm: LlamaIndexLLMWrapper
    ragas_embeddings: HuggingFaceEmbeddings

    ragas_llm, ragas_embeddings = load_ragas_models()

    # Load the index created with the selected chunking strategy
    index: VectorStoreIndex = get_or_build_index(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        embed_model=embed_model_to_test,
    )

    # Store results from every reranker configuration
    all_results: list[pd.DataFrame] = []

    # Test every reranker configuration
    for config in RERANKER_CONFIGS:

        retriever_k: int = config["retriever_k"]
        reranker_n: int = config["reranker_n"]

        print(
            "\n--- Testing reranker configuration: "
            f"retriever_k={retriever_k}, "
            f"reranker_n={reranker_n} ---"
        )

        # Stage 1:
        # Retrieve a broad set of candidate chunks
        retriever = index.as_retriever(
            similarity_top_k=retriever_k,
        )

        # Stage 2:
        # Rerank the candidate chunks with a cross-encoder
        reranker: SentenceTransformerRerank = (
            SentenceTransformerRerank(
                top_n=reranker_n,
                model=RERANKER_MODEL_NAME,
            )
        )

        # Build the retrieval, reranking and generation pipeline
        query_engine: RetrieverQueryEngine = (
            RetrieverQueryEngine.from_args(
                retriever=retriever,
                node_postprocessors=[reranker],
                llm=llm_to_test,
            )
        )

        # Generate answers and collect reranked contexts
        qa_dataset: Dataset = generate_qa_dataset(
            query_engine=query_engine,
            questions=questions,
            ground_truths=ground_truths,
        )

        print(
            "--- Running Ragas evaluation for "
            f"retriever_k={retriever_k}, "
            f"reranker_n={reranker_n} ---"
        )

        # Evaluate using the configured Ragas metrics
        results_df: pd.DataFrame = evaluate_with_rate_limit(
            qa_dataset=qa_dataset,
            ragas_llm=ragas_llm,
            ragas_embeddings=ragas_embeddings,
        )

        # Record the complete experimental configuration
        results_df["chunk_size"] = CHUNK_SIZE
        results_df["chunk_overlap"] = CHUNK_OVERLAP
        results_df["retriever_k"] = retriever_k
        results_df["reranker_n"] = reranker_n
        results_df["reranker_model"] = RERANKER_MODEL_NAME

        all_results.append(results_df)

    # Combine all reranker results
    final_df: pd.DataFrame = pd.concat(
        all_results,
        ignore_index=True,
    )

    # Save detailed and summary results
    save_results(
        results_df=final_df,
        filename_prefix="reranker_evaluation",
    )

    print(
        "--- ✅ Treasoria Reranker Strategy "
        "Evaluation Complete ---"
    )

def evaluate_query_rewriting() -> None:
    """
    Compare the best Treasoria RAG pipeline with and without HyDE.

    Both experiments use the selected chunking and reranking
    configuration. The only changed parameter is query rewriting.
    """

    print(
        "--- 🚀 Stage 4: Evaluating Treasoria "
        "Query Rewriting (HyDE) ---"
    )

    # ========================================================
    # STEP 1: LOAD THE PRODUCT MODELS
    # ========================================================

    # LLM used to generate Treasoria answers and hypothetical
    # HyDE documents
    llm_to_test: Groq = initialise_llm()

    # Embedding model used for indexing and retrieval
    embed_model_to_test: HuggingFaceEmbedding = (
        get_embedding_model()
    )

    # ========================================================
    # STEP 2: LOAD THE EVALUATION DATA
    # ========================================================

    questions: list[str]
    ground_truths: list[str]

    questions, ground_truths = get_evaluation_data()

    print(
        f"--- Loaded {len(questions)} evaluation "
        "question(s) ---"
    )

    # ========================================================
    # STEP 3: LOAD THE BEST CONFIGURATION
    # ========================================================

    best_retriever_k: int = (
        BEST_RERANKER_STRATEGY["retriever_k"]
    )
    best_reranker_n: int = (
        BEST_RERANKER_STRATEGY["reranker_n"]
    )

    # Load the index created with the selected chunking strategy:
    # chunk_size=1024 and chunk_overlap=200
    index: VectorStoreIndex = get_or_build_index(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        embed_model=embed_model_to_test,
    )

    # ========================================================
    # STEP 4: LOAD THE INDEPENDENT RAGAS JUDGE
    # ========================================================

    print(
        "--- 🧠 Loading Ragas LLM and embeddings... ---"
    )

    ragas_llm: LlamaIndexLLMWrapper
    ragas_embeddings: HuggingFaceEmbeddings

    ragas_llm, ragas_embeddings = load_ragas_models()

    # Store the results from both experiments
    all_results: list[pd.DataFrame] = []

    # ========================================================
    # STEP 5: TEST WITHOUT AND WITH HYDE
    # ========================================================

    for use_hyde in [False, True]:

        print(
            "\n--- Testing query-rewriting configuration: "
            f"use_hyde={use_hyde} ---"
        )

        # Broad vector retrieval:
        # retrieve the 10 closest candidate chunks
        retriever = index.as_retriever(
            similarity_top_k=best_retriever_k,
        )

        # Precise reranking:
        # retain the 2 best chunks
        reranker: SentenceTransformerRerank = (
            SentenceTransformerRerank(
                top_n=best_reranker_n,
                model=RERANKER_MODEL_NAME,
            )
        )

        # Create the standard retriever + reranker query engine
        base_query_engine: BaseQueryEngine = (
            RetrieverQueryEngine.from_args(
                retriever=retriever,
                node_postprocessors=[reranker],
                llm=llm_to_test,
            )
        )

        # Add HyDE only during the second experiment
        if use_hyde:
            hyde_transform: HyDEQueryTransform = (
                HyDEQueryTransform(
                    llm=llm_to_test,
                    include_original=True,
                )
            )

            query_engine: BaseQueryEngine = (
                TransformQueryEngine(
                    query_engine=base_query_engine,
                    query_transform=hyde_transform,
                )
            )

        else:
            query_engine = base_query_engine

        # ====================================================
        # STEP 6: GENERATE ANSWERS AND RETRIEVED CONTEXTS
        # ====================================================

        qa_dataset: Dataset = generate_qa_dataset(
            query_engine=query_engine,
            questions=questions,
            ground_truths=ground_truths,
        )

        # ====================================================
        # STEP 7: RUN THE RAGAS EVALUATION
        # ====================================================

        print(
            "--- Running Ragas evaluation for "
            f"use_hyde={use_hyde} ---"
        )

        results_df: pd.DataFrame = evaluate_with_rate_limit(
            qa_dataset=qa_dataset,
            ragas_llm=ragas_llm,
            ragas_embeddings=ragas_embeddings,
        )

        # ====================================================
        # STEP 8: RECORD THE TESTED CONFIGURATION
        # ====================================================

        results_df["chunk_size"] = CHUNK_SIZE
        results_df["chunk_overlap"] = CHUNK_OVERLAP
        results_df["retriever_k"] = best_retriever_k
        results_df["reranker_n"] = best_reranker_n
        results_df["use_hyde"] = use_hyde
        results_df["reranker_model"] = RERANKER_MODEL_NAME

        all_results.append(results_df)

    # ========================================================
    # STEP 9: COMBINE AND SAVE THE RESULTS
    # ========================================================

    final_df: pd.DataFrame = pd.concat(
        all_results,
        ignore_index=True,
    )

    save_results(
        results_df=final_df,
        filename_prefix="query_rewrite_evaluation",
    )

    print(
        "--- ✅ Treasoria Query Rewriting "
        "Evaluation Complete ---"
    ) 