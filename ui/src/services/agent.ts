import api from "./index";

export const agentApi = {
  loginIn: () => api.get(`/web/api/login`),
  getWhiteList: () => api.get(`/web/api/getWhiteList`),
  apply: (data: string) => api.get(`/web/api/genie/apply`, { email: data }),
  allModels: () => api.get(`/data/allModels`),
  previewData: (modelCode: string) => api.get(`/data/previewData?modelCode=${modelCode}`),
};

export interface KnowledgeRAGRequest {
  requestId?: string;
  task: string;
  filePaths?: string[];
}

export interface KnowledgeRAGResponse {
  code?: number;
  data?: string;
  requestId?: string;
  error?: string;
}

export interface RetrievalResult {
  score: number;
  content: string;
  fileName: string;
  chunkIndex: number;
}

export interface KnowledgeStats {
  totalChunks: number;
  totalFiles: number;
  lastUpdate: string | null;
}

export const knowledgeRAGApi = {
  query: (data: KnowledgeRAGRequest) =>
    api.post<KnowledgeRAGResponse>(`/v1/knowledge/query`, data),

  queryStream: (data: KnowledgeRAGRequest) =>
    api.post<KnowledgeRAGResponse>(`/v1/knowledge/query_stream`, data),

  querySync: (data: KnowledgeRAGRequest) =>
    api.post<KnowledgeRAGResponse>(`/v1/knowledge/query`, data),

  deleteFile: (filePath: string) =>
    api.delete(`/v1/knowledge/file`, { filePath }),

  clearKnowledgeBase: () =>
    api.delete(`/v1/knowledge/clear`),

  syncKnowledgeBase: () =>
    api.post(`/v1/knowledge/sync`),

  getStats: () =>
    api.get<KnowledgeStats>(`/v1/knowledge/stats`),
};

export async function queryKnowledgeRAGSync(
  request: KnowledgeRAGRequest
): Promise<string> {
  const response = await knowledgeRAGApi.querySync(request) as unknown as { code?: number; data?: string; error?: string };

  if (response.code === 200) {
    return response.data || "";
  }

  throw new Error(response.error || "Query failed");
}