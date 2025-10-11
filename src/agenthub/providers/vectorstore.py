"""Mock vectorstore for retrieve_doc tool."""

from typing import Dict, List


class MockVectorStore:
    """Simple in-memory mock vectorstore."""

    def __init__(self) -> None:
        """Initialize mock vectorstore with sample data."""
        self.documents: Dict[str, Dict[str, str]] = {
            "doc_001": {
                "title": "Q4 2024 Marketing Report",
                "content": "Q4 saw a 23% increase in ROAS with top campaigns in tech vertical.",
            },
            "doc_002": {
                "title": "Advertiser 123 Campaign Analysis",
                "content": "Advertiser 123 achieved 3.2x ROAS over 7 days with $50K spend.",
            },
            "doc_003": {
                "title": "Budget Optimization Guide",
                "content": "Best practices for budget allocation across campaigns and ad groups.",
            },
        }

    def retrieve(self, doc_id: str) -> Dict[str, str]:
        """Retrieve a document by ID.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Document dict with title and content
        """
        if doc_id in self.documents:
            return self.documents[doc_id]
        return {"title": "Not Found", "content": f"Document {doc_id} not found."}

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        """Search documents by query (simple keyword match).
        
        Args:
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of document dicts
        """
        # Simple keyword matching
        query_lower = query.lower()
        results = []

        for doc_id, doc in self.documents.items():
            content = (doc["title"] + " " + doc["content"]).lower()
            if any(word in content for word in query_lower.split()):
                results.append({"id": doc_id, **doc})

        return results[:top_k]


# Global instance
mock_vectorstore = MockVectorStore()

