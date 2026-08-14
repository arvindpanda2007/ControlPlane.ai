from dotenv import load_dotenv

from controlplane.shadow.worker import ShadowWorker


load_dotenv()


worker = ShadowWorker()


worker.evaluate_trace(
    "8ce38615-d6b9-4387-996d-3d7877a33624"
)