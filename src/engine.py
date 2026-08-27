# Import Path to create operating-system-independent paths
from pathlib import Path

# Import Python's high-precision timer
import time

# Import the main LlamaIndex components used to load documents,
# build an index, manage its storage and reload it later
from llama_index.core import (
    StorageContext,
    SimpleDirectoryReader,
    VectorStoreIndex,
    load_index_from_storage,
)

# Import the advanced conversational chat engine
from llama_index.core.chat_engine import (
    ContextChatEngine,
)

# Import the conversation-memory buffer
from llama_index.core.memory import ChatMemoryBuffer

# Import the text splitter used to create overlapping chunks
from llama_index.core.node_parser import SentenceSplitter

# Import the cross-encoder reranker
from llama_index.core.postprocessor import (
    SentenceTransformerRerank,
)

# Import the document type used for loaded source files
from llama_index.core.schema import Document

# Import the Hugging Face embedding model type
from llama_index.embeddings.huggingface import (
    HuggingFaceEmbedding,
)

# Import the Groq LLM type
from llama_index.llms.groq import Groq

# Import the RAG, reranker, memory and path configurations
from src.config import (
    CHAT_MEMORY_TOKEN_LIMIT,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DATA_PATH,
    LLM_SYSTEM_PROMPT,
    RERANKER_MODEL_NAME,
    RERANKER_TOP_N,
    SIMILARITY_TOP_K,
    VECTOR_STORE_PATH,
)

# Import the model-loading functions
from src.model_loader import (
    get_embedding_model,
    initialise_llm,
)

# Import the structured SQL financial-question handler
from src.sql_engine import (
    answer_sql_question,
)


def _create_new_vector_store(
    embed_model: HuggingFaceEmbedding,
) -> VectorStoreIndex:
    """
    Create, save and return a new vector store from the
    selected Treasoria sources.
    """

    print(
        "Creating a new vector store from the selected "
        "Treasoria sources..."
    )

    # ========================================================
    # STEP 1: LOCATE THE STRUCTURED DATASET
    # ========================================================

    # Search inside data/ for the Treasoria dataset directory.
    #
    # The wildcard allows the code to work even if the full
    # directory name is slightly different.
    dataset_directories: list[Path] = [
        directory
        for directory in DATA_PATH.glob(
            "Treasoria_Datasets*"
        )
        if directory.is_dir()
    ]

    # Stop with a clear message if the dataset folder
    # cannot be found
    if not dataset_directories:
        raise FileNotFoundError(
            "Treasoria dataset directory not found "
            "inside data/."
        )

    # Use the first matching dataset directory
    dataset_path: Path = dataset_directories[0]

    print(
        "Structured dataset found: "
        f"{dataset_path.name}"
    )

    # ========================================================
    # STEP 2: SELECT THE DOCUMENTARY SOURCES
    # ========================================================

    # Add the company identity and the main Treasoria
    # documentation currently stored directly inside data/.
    #
    # Missing files are filtered out later, so the code also
    # works when these documents live only inside dataset/docs/.
    rag_source_files: list[Path] = [
        DATA_PATH / "company_profile.json",
        DATA_PATH / "DATA_DICTIONARY.md",
        DATA_PATH / "README.md",
        DATA_PATH / "VALIDATION_REPORT.md",
    ]

    # ========================================================
    # STEP 3: ADD THE GOLD ANALYTICAL TABLES
    # ========================================================

    # The Gold layer contains the final financial tables,
    # KPIs, cash positions, monthly cash flows and aging tables.
    gold_path: Path = dataset_path / "gold"

    if gold_path.exists():
        rag_source_files.extend(
            sorted(
                gold_path.glob("*.csv")
            )
        )
    else:
        print(
            "Warning: Gold directory not found at "
            f"{gold_path}"
        )

    # ========================================================
    # STEP 4: ADD THE DATASET DOCUMENTATION
    # ========================================================

    # Load the Markdown documentation stored in the
    # dataset's docs/ directory.
    documentation_path: Path = (
        dataset_path / "docs"
    )

    if documentation_path.exists():
        rag_source_files.extend(
            sorted(
                documentation_path.glob("*.md")
            )
        )
    else:
        print(
            "Warning: Documentation directory "
            f"not found at {documentation_path}"
        )

    # ========================================================
    # STEP 5: REMOVE MISSING OR DUPLICATED FILES
    # ========================================================

    existing_rag_source_files: list[Path] = []

    for source_file in rag_source_files:
        if (
            source_file.exists()
            and source_file
            not in existing_rag_source_files
        ):
            existing_rag_source_files.append(
                source_file
            )

    # Stop if no usable source file was found
    if not existing_rag_source_files:
        raise ValueError(
            "No RAG source files were found."
        )

    print("--- RAG sources selected ---")

    # Print every source included in the vector index.
    # This provides traceability when rebuilding the index.
    for source_file in existing_rag_source_files:
        print(
            "- "
            f"{source_file.relative_to(DATA_PATH)}"
        )

    # ========================================================
    # STEP 6: LOAD THE SELECTED SOURCES
    # ========================================================

    # Load only:
    # - the company profile;
    # - the main documentation;
    # - the Gold analytical tables;
    # - the dataset documentation.
    #
    # Bronze, Silver, scripts, PDFs and SQLite are intentionally
    # excluded from the vector index to avoid duplication and an
    # excessively large RAG index.
    documents: list[Document] = (
        SimpleDirectoryReader(
            input_files=[
                source_file.as_posix()
                for source_file
                in existing_rag_source_files
            ],
        ).load_data()
    )

    # Stop with a clear error if no document was loaded
    if not documents:
        raise ValueError(
            "The selected source files could not "
            "be loaded."
        )

    print(
        f"Loaded {len(documents)} document(s) "
        "for the RAG index."
    )

    # ========================================================
    # STEP 7: SPLIT THE DOCUMENTS INTO CHUNKS
    # ========================================================

    # Split documents using the configuration defined
    # in src/config.py.
    text_splitter: SentenceSplitter = (
        SentenceSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
    )

    # ========================================================
    # STEP 8: BUILD THE VECTOR INDEX
    # ========================================================

    # Split the documents, generate embeddings and create
    # the vector index.
    index: VectorStoreIndex = (
        VectorStoreIndex.from_documents(
            documents,
            transformations=[text_splitter],
            embed_model=embed_model,
        )
    )

    # ========================================================
    # STEP 9: SAVE THE VECTOR INDEX
    # ========================================================

    # Persist the index to the configuration-specific
    # vector-store directory.
    index.storage_context.persist(
        persist_dir=VECTOR_STORE_PATH.as_posix(),
    )

    print(
        "Vector store created and saved with "
        f"chunk_size={CHUNK_SIZE} and "
        f"chunk_overlap={CHUNK_OVERLAP}!"
    )

    return index


def get_vector_store(
    embed_model: HuggingFaceEmbedding,
) -> VectorStoreIndex:
    """
    Load the selected vector store if it exists.

    Otherwise, create and save a new vector store using the
    chunking configuration defined in src/config.py.
    """

    # Create the configuration-specific directory if necessary
    VECTOR_STORE_PATH.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Load the index if this directory already contains one
    if any(VECTOR_STORE_PATH.iterdir()):
        print(
            "Loading existing vector store from disk: "
            f"{VECTOR_STORE_PATH.name}"
        )

        # Connect LlamaIndex to the persisted index directory
        storage_context: StorageContext = (
            StorageContext.from_defaults(
                persist_dir=(
                    VECTOR_STORE_PATH.as_posix()
                ),
            )
        )

        # Reload the existing vector index using the same
        # embedding model
        return load_index_from_storage(
            storage_context,
            embed_model=embed_model,
        )

    # Build a new index when the directory is empty
    return _create_new_vector_store(
        embed_model=embed_model,
    )


def get_chat_engine(
    llm: Groq,
    embed_model: HuggingFaceEmbedding,
) -> ContextChatEngine:
    """
    Initialise the Treasoria conversational RAG engine.

    The engine retrieves candidate chunks, reranks them,
    keeps the best chunks and generates a grounded response.
    """

    # Create or load the selected vector index
    vector_index: VectorStoreIndex = (
        get_vector_store(
            embed_model=embed_model,
        )
    )

    # ========================================================
    # STEP 1: CREATE THE RETRIEVER
    # ========================================================

    # Retrieve a broad set of candidate chunks from the
    # vector index.
    retriever = vector_index.as_retriever(
        similarity_top_k=SIMILARITY_TOP_K,
    )

    # ========================================================
    # STEP 2: CREATE THE RERANKER
    # ========================================================

    # Re-evaluate the candidate chunks using the cross-encoder
    # and retain only the most relevant chunks.
    reranker: SentenceTransformerRerank = (
        SentenceTransformerRerank(
            top_n=RERANKER_TOP_N,
            model=RERANKER_MODEL_NAME,
        )
    )

    # ========================================================
    # STEP 3: CREATE THE CONVERSATIONAL MEMORY
    # ========================================================

    memory: ChatMemoryBuffer = (
        ChatMemoryBuffer.from_defaults(
            token_limit=CHAT_MEMORY_TOKEN_LIMIT,
        )
    )

    # ========================================================
    # STEP 4: ASSEMBLE THE CHAT ENGINE
    # ========================================================

    # ContextChatEngine avoids the additional question-
    # condensation request that previously caused long
    # response times.
    chat_engine: ContextChatEngine = (
        ContextChatEngine.from_defaults(
            retriever=retriever,
            llm=llm,
            memory=memory,
            system_prompt=LLM_SYSTEM_PROMPT,
            node_postprocessors=[reranker],
        )
    )

    return chat_engine


def main_chat_loop() -> None:
    """
    Run the hybrid Treasoria SQL + RAG Financial Assistant
    and measure initialisation and response times.

    Structured financial questions are answered through
    SQLite when supported by the SQL layer.

    Questions that require documentary context or explanation
    automatically fall back to the conversational RAG engine.
    """

    # Start measuring the full application initialisation
    initialisation_start: float = (
        time.perf_counter()
    )

    print("--- Initialising models... ---")

    # Load the generator LLM
    llm: Groq = initialise_llm()

    # Load the embedding model used for semantic retrieval
    embed_model: HuggingFaceEmbedding = (
        get_embedding_model()
    )

    # Create the advanced RAG chat engine
    chat_engine: ContextChatEngine = (
        get_chat_engine(
            llm=llm,
            embed_model=embed_model,
        )
    )

    # Calculate the total initialisation time
    initialisation_time: float = (
        time.perf_counter()
        - initialisation_start
    )

    print(
        "--- Advanced Treasoria Assistant Initialised. ---"
    )

    print(
        f"Chunking: {CHUNK_SIZE}/{CHUNK_OVERLAP} | "
        f"Retrieve: {SIMILARITY_TOP_K} | "
        f"Rerank: {RERANKER_TOP_N}"
    )

    print(
        f"Initialisation time: "
        f"{initialisation_time:.3f} seconds"
    )

    print(
        "Type 'exit' or 'quit' to end "
        "the conversation."
    )

    # ========================================================
    # INTERACTIVE CHAT LOOP
    # ========================================================

    while True:

        # Read and clean the user's question
        user_input: str = input(
            "\nYou: "
        ).strip()

        # Stop the chatbot
        if user_input.lower() in [
            "exit",
            "quit",
        ]:
            print("\nBot: Goodbye!")
            break

        # Ignore empty user inputs
        if not user_input:
            continue

        # Start measuring the response duration
        response_start: float = (
            time.perf_counter()
        )

        # ====================================================
        # HYBRID SQL + RAG ROUTING
        # ====================================================

        # First try the structured SQL layer.
        #
        # This handles questions requiring exact calculations
        # such as counts, sums, balances and averages.
        sql_response: str | None = (
            answer_sql_question(
                user_input
            )
        )

        if sql_response is not None:

            # The structured database supplied an exact answer.
            response = sql_response

        else:

            # The SQL layer does not recognise this question.
            #
            # Fall back to the existing RAG pipeline to retrieve
            # relevant context, rerank it and generate a grounded
            # conversational answer.
            response = chat_engine.chat(
                user_input
            )

        # Calculate the response duration
        response_time: float = (
            time.perf_counter()
            - response_start
        )

        # Display the chatbot's answer.
        #
        # The internal SQL/RAG route is intentionally hidden
        # from the user so the assistant remains natural.
        print(
            f"\nBot: {response}"
        )

        print(
            f"\nResponse time: "
            f"{response_time:.3f} seconds"
        )