## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

* [Node.js](https://nodejs.org/) (v18.x or higher)
* [Python](https://www.python.org/) (v3.12.6)
* [Package Manager](https://www.npmjs.com/): npm, yarn, pnpm, or bun

---

## 📦 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/noelquadras/ai-multi-agent.git
cd ai-multi-agent

```

### 2. Backend Setup

It is recommended to use a virtual environment.

```bash
# Navigate to root
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

```

### 3. Frontend Setup

```bash
cd frontend/software-agent
npm install

```

---

## 🏃 Usage

You will need two terminal windows to run the full stack simultaneously.

### Start Backend

From the **root** folder:

```bash
uvicorn app:app --reload --port 8000

```

> The API will be available at: `http://localhost:8000`

### Start Frontend

From `frontend/software-agent`:

```bash
npm run dev

```

> The application will be available at: `http://localhost:3000`

---

## 📂 Project Structure

```text
.
├── app.py                # Backend entry point
├── main.py               # Main
├── requirements.txt      # Python dependencies
├── venv/                 # Virtual environment (ignored by git)
└── frontend/
    └── software-agent/   # Next.js/React application
        ├── src/
        ├── public/
        └── package.json

```
