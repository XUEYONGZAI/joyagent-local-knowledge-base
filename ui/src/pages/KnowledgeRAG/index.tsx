import React, { useState, useRef, useEffect } from 'react';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  SyncOutlined,
  PlusOutlined,
  FolderOpenOutlined,
  FileOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  FileExcelOutlined,
  FilePptOutlined,
  FileMarkdownOutlined,
  DatabaseOutlined,
  InfoCircleOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  Upload as AntdUpload,
  Input,
  Button,
  Card,
  List,
  Space,
  Tag,
  Modal,
  message,
  Spin,
  Tooltip,
  Typography,
  Badge,
  Empty,
  Alert,
} from 'antd';
import type { UploadProps } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './index.css';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

const generateId = (): string => {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
};

interface FileItem {
  uid: string;
  name: string;
  status: 'pending' | 'uploading' | 'done' | 'error';
  size?: number;
  type?: string;
  path?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  files?: FileItem[];
}

interface RetrievalResult {
  score: number;
  content: string;
  fileName: string;
  chunkIndex: number;
}

const API_BASE = '/v1/knowledge';

const getFileIcon = (fileName: string) => {
  const ext = fileName.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'pdf':
      return <FilePdfOutlined style={{ color: '#ff4d4f' }} />;
    case 'doc':
    case 'docx':
      return <FileWordOutlined style={{ color: '#1890ff' }} />;
    case 'xls':
    case 'xlsx':
      return <FileExcelOutlined style={{ color: '#52c41a' }} />;
    case 'ppt':
    case 'pptx':
      return <FilePptOutlined style={{ color: '#fa8c16' }} />;
    case 'md':
      return <FileMarkdownOutlined style={{ color: '#722ed1' }} />;
    default:
      return <FileOutlined />;
  }
};

const KnowledgeRAGPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [fileList, setFileList] = useState<FileItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [retrievalResults, setRetrievalResults] = useState<RetrievalResult[]>([]);
  const [showRetrievalDetails, setShowRetrievalDetails] = useState(false);
  const [stats, setStats] = useState({
    totalChunks: 0,
    totalFiles: 0,
    lastUpdate: null as string | null,
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollToBottom();
    fetchStats();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleFileUpload: UploadProps['customRequest'] = async (options) => {
    const { file } = options;
    const fileItem = file as unknown as FileItem;
    // 使用 customUid，因为 beforeUpload 中设置的是 customUid
    const uid = (file as any).customUid || fileItem.uid;

    try {
      const formData = new FormData();
      formData.append('file', file as File);

      setFileList((prev) =>
        prev.map((f) =>
          f.uid === uid ? { ...f, status: 'uploading' } : f
        )
      );

      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        setFileList((prev) =>
          prev.map((f) =>
            f.uid === uid
              ? { ...f, status: 'done', path: result.data?.filePath || fileItem.name }
              : f
          )
        );
        message.success(`${fileItem.name} 上传成功`);
        fetchStats();
      } else {
        throw new Error('Upload failed');
      }
    } catch (error) {
      setFileList((prev) =>
        prev.map((f) =>
          f.uid === uid ? { ...f, status: 'error' } : f
        )
      );
      message.error(`${fileItem.name} 上传失败`);
    }
  };

  const handleRemoveFile = (uid: string) => {
    const file = fileList.find((f) => f.uid === uid);
    if (file?.path) {
      fetch(`${API_BASE}/file`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filePath: file.path }),
      }).catch(console.error);
      fetchStats();
    }
    setFileList((prev) => prev.filter((f) => f.uid !== uid));
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() && fileList.length === 0) {
      message.warning('请输入问题或上传文件');
      return;
    }

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
      files: fileList.filter((f) => f.status === 'done'),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setRetrievalResults([]);

    try {
      const filePaths = fileList
        .filter((f) => f.status === 'done' && f.path)
        .map((f) => f.path as string);

      const assistantMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      const response = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          requestId: userMessage.id,
          task: inputValue,
          filePaths: filePaths,
        }),
      });

      if (response.ok && response.headers.get('Content-Type')?.includes('text/event-stream')) {
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        while (reader) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') {
                setIsLoading(false);
              } else {
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.content) {
                    assistantMessage.content += parsed.content;
                    setMessages((prev) => {
                      const updated = [...prev];
                      const lastIndex = updated.length - 1;
                      if (lastIndex >= 0 && updated[lastIndex].id === assistantMessage.id) {
                        updated[lastIndex] = { ...assistantMessage };
                      }
                      return updated;
                    });
                  }
                  if (parsed.retrievalResults) {
                    setRetrievalResults(parsed.retrievalResults);
                  }
                } catch (e) {
                  console.error('Parse error:', e);
                }
              }
            }
          }
        }
      } else {
        const result = await response.json();
        if (result.data) {
          assistantMessage.content = result.data;
          setMessages((prev) => {
            const updated = [...prev];
            const lastIndex = updated.length - 1;
            if (lastIndex >= 0 && updated[lastIndex].id === assistantMessage.id) {
              updated[lastIndex] = { ...assistantMessage };
            }
            return updated;
          });
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      message.error('查询失败，请重试');

      setMessages((prev) =>
        prev.map((m) =>
          m.id === userMessage.id ? { ...m, content: m.content + '\n\n[查询失败]' } : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearKnowledgeBase = () => {
    Modal.confirm({
      title: '确认清空知识库',
      content: '确定要清空所有已上传的文件吗？此操作不可恢复。',
      okText: '确认清空',
      okType: 'danger',
      onOk: async () => {
        try {
          const response = await fetch(`${API_BASE}/clear`, { method: 'DELETE' });
          if (response.ok) {
            message.success('知识库已清空');
            setFileList([]);
            setMessages([]);
            setStats({ totalChunks: 0, totalFiles: 0, lastUpdate: null });
          }
        } catch (error) {
          message.error('清空失败');
        }
      },
    });
  };

  const handleSyncKnowledgeBase = async () => {
    try {
      message.loading('正在同步...');
      const response = await fetch(`${API_BASE}/sync`, { method: 'POST' });
      if (response.ok) {
        message.success('同步完成');
        fetchStats();
      }
    } catch (error) {
      message.error('同步失败');
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/stats`);
      if (response.ok) {
        const result = await response.json();
        if (result.data) {
          setStats({
            totalFiles: result.data.totalFiles || 0,
            totalChunks: result.data.totalChunks || 0,
            lastUpdate: result.data.lastUpdate || null,
          });
        }
      }
    } catch (error) {
      console.error('Fetch stats error:', error);
    }
  };

  return (
    <div className="knowledge-rag-container">
      <div className="knowledge-rag-header">
        <div className="header-left">
          <DatabaseOutlined size={20} />
          <Title level={4} style={{ margin: 0 }}>本地知识库</Title>
        </div>
        <div className="header-right">
          <Space>
            <Tooltip title="同步知识库">
              <Button
                icon={<SyncOutlined spin={isLoading} />}
                onClick={handleSyncKnowledgeBase}
                disabled={isLoading}
              >
                同步
              </Button>
            </Tooltip>
            <Tooltip title="清空知识库">
              <Button
                icon={<DeleteOutlined />}
                onClick={handleClearKnowledgeBase}
                danger
                disabled={isLoading}
              >
                清空
              </Button>
            </Tooltip>
          </Space>
        </div>
      </div>

      <div className="knowledge-rag-content">
        <div className="knowledge-rag-sidebar">
          <Card
            size="small"
            title={
              <Space>
                <FolderOpenOutlined />
                <span>已上传文件</span>
                <Badge count={fileList.length} style={{ marginLeft: 8 }} />
              </Space>
            }
            extra={
              <AntdUpload
                accept=".txt,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.md"
                showUploadList={false}
                customRequest={handleFileUpload}
                beforeUpload={(file) => {
                  const newFile: FileItem = {
                    uid: generateId(),
                    name: file.name,
                    status: 'pending',
                    size: file.size,
                    type: file.type,
                  };
                  setFileList((prev) => [...prev, newFile]);
                  // 将 uid 存储到文件对象上，以便在 customRequest 中使用
                  (file as any).customUid = newFile.uid;
                  // 返回 true 让 customRequest 被调用
                  return true;
                }}
              >
                <Button size="small" icon={<PlusOutlined />} type="text">
                  添加
                </Button>
              </AntdUpload>
            }
            style={{ marginBottom: 16 }}
          >
            {fileList.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无上传文件"
              />
            ) : (
              <List
                size="small"
                dataSource={fileList}
                renderItem={(file) => (
                  <List.Item
                    key={file.uid}
                    actions={[
                      <Tooltip title="移除">
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => handleRemoveFile(file.uid)}
                        />
                      </Tooltip>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={getFileIcon(file.name)}
                      title={<Text ellipsis style={{ maxWidth: 120 }}>{file.name}</Text>}
                      description={
                        <Space size="small">
                          {file.status === 'done' && (
                            <Tag color="success" style={{ margin: 0 }}>已上传</Tag>
                          )}
                          {file.status === 'uploading' && (
                            <Tag color="processing" style={{ margin: 0 }}>上传中</Tag>
                          )}
                          {file.status === 'error' && (
                            <Tag color="error" style={{ margin: 0 }}>失败</Tag>
                          )}
                          {file.size && (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {(file.size / 1024).toFixed(1)} KB
                            </Text>
                          )}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>

          <Card size="small" title={<Space><InfoCircleOutlined /><span>知识库统计</span></Space>}>
            <div className="stats-container">
              <div className="stat-item">
                <Text type="secondary">文件数</Text>
                <Text strong>{stats.totalFiles}</Text>
              </div>
              <div className="stat-item">
                <Text type="secondary">Chunk数</Text>
                <Text strong>{stats.totalChunks}</Text>
              </div>
              {stats.lastUpdate && (
                <div className="stat-item">
                  <Text type="secondary">最后更新</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {stats.lastUpdate}
                  </Text>
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="knowledge-rag-main">
          <div className="chat-container" ref={chatContainerRef}>
            {messages.length === 0 ? (
              <div className="welcome-container">
                <div className="welcome-icon">
                  <DatabaseOutlined size={64} style={{ color: '#1890ff' }} />
                </div>
                <Title level={3}>欢迎使用本地知识库</Title>
                <Paragraph type="secondary">
                  上传文档后，可以针对文档内容进行问答，支持以下功能：
                </Paragraph>
                <div className="feature-list">
                  <div className="feature-item">
                    <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                    <span>多格式文档支持（PDF、Word、Excel、PPT、Markdown等）</span>
                  </div>
                  <div className="feature-item">
                    <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                    <span>语义检索与智能问答</span>
                  </div>
                  <div className="feature-item">
                    <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                    <span>流式输出响应</span>
                  </div>
                  <div className="feature-item">
                    <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
                    <span>增量更新与同步</span>
                  </div>
                </div>
                {fileList.filter((f) => f.status === 'done').length === 0 && (
                  <Alert
                    type="info"
                    showIcon
                    icon={<CloudUploadOutlined />}
                    message="建议先上传文档"
                    description="点击左侧「添加」按钮上传文档，然后开始提问"
                    style={{ marginTop: 24, maxWidth: 400 }}
                  />
                )}
              </div>
            ) : (
              <div className="message-list">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`message-item ${msg.role === 'user' ? 'user-message' : 'assistant-message'}`}
                  >
                    <div className="message-avatar">
                      {msg.role === 'user' ? (
                        <div className="user-avatar">U</div>
                      ) : (
                        <div className="assistant-avatar">
                          <DatabaseOutlined size={20} />
                        </div>
                      )}
                    </div>
                    <div className="message-content">
                      {msg.files && msg.files.length > 0 && (
                        <div className="message-files">
                          <Space wrap>
                            {msg.files.map((file) => (
                              <Tag key={file.uid} icon={getFileIcon(file.name)}>
                                {file.name}
                              </Tag>
                            ))}
                          </Space>
                        </div>
                      )}
                      <div className="message-text">
                        {msg.role === 'assistant' ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        ) : (
                          msg.content
                        )}
                      </div>
                      <div className="message-time">
                        {msg.timestamp.toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))}
                {isLoading && (
                  <div className="message-item assistant-message">
                    <div className="message-avatar">
                      <div className="assistant-avatar">
                        <DatabaseOutlined size={20} />
                      </div>
                    </div>
                    <div className="message-content">
                      <Spin indicator={<LoadingOutlined style={{ fontSize: 20 }} spin />} />
                      <Text type="secondary" style={{ marginLeft: 8 }}>正在思考...</Text>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <div className="input-container">
            <div className="input-wrapper">
              <AntdUpload
                accept=".txt,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.md"
                showUploadList={false}
                customRequest={handleFileUpload}
                beforeUpload={(file) => {
                  const newFile: FileItem = {
                    uid: generateId(),
                    name: file.name,
                    status: 'pending',
                    size: file.size,
                    type: file.type,
                  };
                  setFileList((prev) => [...prev, newFile]);
                  return false;
                }}
              >
                <Button icon={<PlusOutlined />} type="text" disabled={isLoading}>
                  上传
                </Button>
              </AntdUpload>
              <TextArea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder="输入问题，按 Enter 发送，Shift+Enter 换行"
                autoSize={{ minRows: 1, maxRows: 4 }}
                disabled={isLoading}
                style={{ flex: 1 }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSendMessage}
                loading={isLoading}
                disabled={!inputValue.trim() && fileList.length === 0}
              >
                发送
              </Button>
            </div>
            {retrievalResults.length > 0 && (
              <div className="retrieval-info">
                <Button
                  type="link"
                  onClick={() => setShowRetrievalDetails(!showRetrievalDetails)}
                >
                  检索到 {retrievalResults.length} 个相关片段
                  {showRetrievalDetails ? ' ▲' : ' ▼'}
                </Button>
                {showRetrievalDetails && (
                  <div className="retrieval-details">
                    {retrievalResults.map((result, index) => (
                      <Card key={index} size="small" style={{ marginTop: 8 }}>
                        <div className="result-header">
                          <Tag color="blue">{result.fileName}</Tag>
                          <Text type="secondary">片段 {result.chunkIndex + 1}</Text>
                          <Text type="secondary">相似度: {(result.score * 100).toFixed(1)}%</Text>
                        </div>
                        <Paragraph
                          ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                          style={{ marginTop: 8, marginBottom: 0 }}
                        >
                          {result.content}
                        </Paragraph>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default KnowledgeRAGPage;