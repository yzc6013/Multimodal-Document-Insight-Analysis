import os
from pathlib import Path
from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain.schema import Document

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field

from langchain import hub
from langchain_core.output_parsers import StrOutputParser

from langchain_community.tools.tavily_search import TavilySearchResults

from langgraph.graph import END, StateGraph, START

from tradingagents.llm_adapters import ChatDashScopeOpenAI

os.environ["DASHSCOPE_API_KEY"] = "sk-647775243b4a4581ae112c3aded81a66"
os.environ["TAVILY_API_KEY"] = "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"

class CRAGServer:
    def __init__(
        self,
        doc_dir: str,
        collection_name: str = "rag-chroma",
    ):

        ### Retrieval
        BASE_DIR = Path(__file__).resolve().parent
        doc_dir = BASE_DIR / doc_dir
        if not doc_dir.exists() or not doc_dir.is_dir():
            raise FileNotFoundError(f"文档目录不存在：{doc_dir}")

        docs: List[Document] = []
        for file in doc_dir.rglob("*.md"):
            docs.extend(TextLoader(str(file), encoding="utf-8").load())

        splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=250,
            chunk_overlap=0,
        )
        doc_splits = splitter.split_documents(docs)

        self.vectorstore = Chroma.from_documents(
            documents=doc_splits,
            collection_name=collection_name,
            embedding=DashScopeEmbeddings(),
        )

        self.retriever = self.vectorstore.as_retriever(
            search_kwargs={
                "k": 10,  # 最终返回 top 10 个最相关文档
            }
        )

        ### Retrieval Grader
        class GradeDocuments(BaseModel):
            """Binary score for relevance check on retrieved documents."""

            binary_score: str = Field(
                description="Documents are relevant to the question, 'yes' or 'no'"
            )

        self.relevance_llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0,
        )
        self.structured_llm_grader = self.relevance_llm.with_structured_output(GradeDocuments)

        self.grade_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """您是一名评分员，用于评估检索到的文档与用户问题的相关性。
                如果文档包含与问题相关的关键词或语义意义，请将其标记为“相关”。
                请给出二元评分——“yes”或“no”，以表明该文档是否与问题相关。"""),
                ("human", "检索文档: \n\n {document} \n\n 用户问题: {question}"),
            ]
        )

        self.retrieval_grader = self.grade_prompt | self.structured_llm_grader

        ### Generate
        self.rag_llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0,
        )

        self.generation_prompt = ChatPromptTemplate.from_messages(
            [
                ("system",
                 "你是一位知识丰富的助手，将根据提供的参考文档回答用户的问题。"
                 "你的回答应详细、有条理，并在可能的情况下引用文档内容。"
                 "请使用中文回答。"),
                ("human",
                 "问题：{question}\n\n 参考文档：\n{context}\n\n请根据这些信息作答。")
            ]
        )

        self.rag_chain = self.generation_prompt | self.rag_llm | StrOutputParser()

        ### Question Re-writer
        self.question_llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0,
        )

        self.re_write_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """你是一名智能的问题重写助手，旨在提升用户查询在网页搜索中的表现。
                请深入分析输入问题，识别其背后的语义意图和真正的信息需求。
                在不改变原始目的或信息内容的前提下，将其改写为更清晰、更具体、更适合搜索引擎处理的表达方式。
                在输出结果中仅仅给出重写后的问题，不要带有其他说明性文字"""),
                (
                    "human",
                    "初始问题: \n\n {question} \n 请将问题优化为更适合检索的形式。",
                ),
            ]
        )

        self.question_rewriter = self.re_write_prompt | self.question_llm | StrOutputParser()

        ### Search
        self.web_search_tool = TavilySearchResults(k=3)

        self.setup()

    def setup(self):
        workflow = StateGraph(CRAGGraphState)

        retrieve_node = create_retrieve_node(self.retriever)
        generate_node = create_generate_node(self.rag_chain)
        grade_documents_node = create_grade_documents_node(self.retrieval_grader)
        transform_query_node = create_transform_query_node(self.question_rewriter)
        web_search_node = create_web_search_node(self.web_search_tool)

        # Define the nodes
        workflow.add_node("retrieve_node", retrieve_node)  # retrieve
        workflow.add_node("generate_node", generate_node)  # grade documents
        workflow.add_node("grade_documents_node", grade_documents_node)  # generate
        workflow.add_node("transform_query_node", transform_query_node)  # transform_query
        workflow.add_node("web_search_node", web_search_node)  # web search

        # Build graph
        workflow.add_edge(START, "retrieve_node")
        workflow.add_edge("retrieve_node", "grade_documents_node")
        workflow.add_conditional_edges(
            "grade_documents_node",
            decide_to_generate,
            {
                "transform_query_node": "transform_query_node",
                "generate_node": "generate_node",
            },
        )
        workflow.add_edge("transform_query_node", "web_search_node")
        workflow.add_edge("web_search_node", "generate_node")
        workflow.add_edge("generate_node", END)

        # Compile
        self.graph = workflow.compile()


from typing_extensions import TypedDict

class CRAGGraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        web_search: whether to add search
        documents: list of documents
    """

    question: str
    generation: str
    web_search: str
    documents: List[str]

def create_retrieve_node(retriever):
    def retrieve_node(state):
        """
        Retrieve documents

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, documents, that contains retrieved documents
        """
        question = state["question"]

        # Retrieval
        documents = retriever.get_relevant_documents(question)
        return {"documents": documents, "question": question}
    return retrieve_node

def create_generate_node(rag_chain):
    def generate_node(state):
        """
        Generate answer

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation, that contains LLM generation
        """
        question = state["question"]
        documents = state["documents"]

        # RAG generation
        generation = rag_chain.invoke({"context": documents, "question": question})
        return {"documents": documents, "question": question, "generation": generation}
    return generate_node

def create_grade_documents_node(retrieval_grader):
    def grade_documents_node(state):
        """
        Determines whether the retrieved documents are relevant to the question.

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): Updates documents key with only filtered relevant documents
        """

        question = state["question"]
        documents = state["documents"]

        # Score each doc
        filtered_docs = []
        web_search = "No"
        for d in documents:
            score = retrieval_grader.invoke(
                {"question": question, "document": d.page_content}
            )
            grade = score.binary_score
            if grade == "yes":
                filtered_docs.append(d)
            else:
                web_search = "Yes"
                continue
        return {"documents": filtered_docs, "question": question, "web_search": web_search}
    return grade_documents_node

def create_transform_query_node(question_rewriter):
    def transform_query(state):
        """
        Transform the query to produce a better question.

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): Updates question key with a re-phrased question
        """

        question = state["question"]
        documents = state["documents"]

        # Re-write question
        better_question = question_rewriter.invoke({"question": question})
        return {"documents": documents, "question": better_question}
    return transform_query

def create_web_search_node(web_search_tool):
    def web_search(state):
        """
        Web search based on the re-phrased question.

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): Updates documents key with appended web results
        """

        question = state["question"]
        documents = state["documents"]

        # Web search
        docs = web_search_tool.invoke({"query": question})
        web_results = "\n".join([d["content"] for d in docs])
        web_results = Document(page_content=web_results)
        documents.append(web_results)

        return {"documents": documents, "question": question}
    return web_search

def decide_to_generate(state):
    """
    Determines whether to generate an answer, or re-generate a question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Binary decision for next node to call
    """

    state["question"]
    web_search = state["web_search"]
    state["documents"]

    if web_search == "Yes":
        # All documents have been filtered check_relevance
        # We will re-generate a new query
        return "transform_query_node"
    else:
        # We have relevant documents, so generate answer
        return "generate_node"


if __name__ == "__main__":
    crag_server = CRAGServer(
        doc_dir="./document",
        collection_name="rag-chroma",
    )

    message = crag_server.graph.invoke({"question": "What are the types of agent memory?"})
    print(message["generation"])