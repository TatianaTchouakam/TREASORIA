# Treasoria

Treasoria is a Streamlit-based application.

## Setup

### 1. Clone the repository

```bash
git clone <REPOSITORY_URL>
cd TREASORIA
```

### 2. Create the Conda environment

Python 3.11 is recommended:

```bash
conda create -n treasoria-env python=3.11
conda activate treasoria-env
```

### 3. Install the dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the Groq API key

The application uses the Groq API. Create a `.env` file in the project root directory:

```text
GROQ_API_KEY=your_groq_api_key
```

Do not commit your API key or `.env` file to the repository.

### 5. Run the application

Start the Streamlit application with:

```bash
streamlit run streamlit_app.py
```

The application will open in your browser.

## Evaluation

To run the evaluation:

```bash
python evaluate.py
```

## Project Structure

```text
TREASORIA/
├── streamlit_app.py       # Streamlit application entry point
├── main.py                # Main application entry point
├── evaluate.py            # Evaluation entry point
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not committed)
├── src/                   # Core application code
├── evaluation/            # Evaluation code
└── data/                  # Datasets and related files
```

## Notes

* Python **3.11** is recommended.
* Store API keys in the `.env` file.
* Never commit `.env` or API keys to the repository.
* When setting up the project on a new machine, create the Conda environment and install the dependencies from `requirements.txt`.
