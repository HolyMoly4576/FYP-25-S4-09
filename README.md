# CSIT314CSR Full Stack Project

## Tech Stack
- **Frontend:** React.js
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL

---

## Folder Structure

.
├── app/ # FastAPI backend
├── frontend/ # React.js frontend
├── migrations/ # DB migrations
├── venv/ # Python virtual environment (don't commit)
├── .env # Environment variables
├── Dockerfile # Backend Docker config
├── docker-compose.yml
├── requirements.txt # Backend Python dependencies
├── seed_data.sql # SQL seed file for DB
└── README.md


---

## Local Development Setup

### 1. Clone the Repository

git clone <your-repo-url>
cd <your-repo-folder>


### 2. Python Backend (FastAPI)

- Ensure Python 3.8+ is installed

#### Create Virtual Environment

python -m venv venv
source venv/bin/activate # macOS/Linux
venv\Scripts\activate # Windows


#### Install Dependencies

pip install -r requirements.txt (I think still empty arh)


#### Run Backend Locally

cd app
uvicorn main:app --reload

*(Replace `main:app` with your actual FastAPI entrypoint)*

---

### 3. Frontend (React.js)

- Ensure Node.js and npm are installed

#### Install React Dependencies

cd frontend
npm install

#### Run Frontend Locally

npm start dev


---

### 4. PostgreSQL Database

- You can run PostgreSQL in Docker with the provided `docker-compose.yml` file.

---

## Docker Setup (Recommended)

### 1. Build and Start All Services

docker-compose up --build (havent set up)


- This will start frontend (React), backend (FastAPI), and PostgreSQL DB as defined in `docker-compose.yml`.
- Check your services by navigating to corresponding ports (e.g., `localhost:8000` for backend, `localhost:3000` for frontend).

### 2. Stopping Docker Containers

docker-compose down


---

## Environment Variables

- Copy `.env.example` to `.env` and fill in your secret keys and DB credentials as needed.

---

## Useful Commands

- Activate Python venv: `source venv/bin/activate`
- Install Python deps: `pip install -r requirements.txt`
- Install frontend deps: `npm install`
- Start backend: `uvicorn main:app --reload`
- Start frontend: `npm start`
- Start everything: `docker-compose up --build`

---

## Database Setup

- To seed database, run the commands in `seed_data.sql` using your PostgreSQL client or as part of the container setup.

---

## Contribution

1. Fork and clone.
2. Create a branch.
3. Commit and raise a pull request.

---

## License

MIT License.
