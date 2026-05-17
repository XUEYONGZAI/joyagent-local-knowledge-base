package com.jd.genie.agent.tool.common;

import com.jd.genie.agent.agent.AgentContext;
import com.jd.genie.agent.tool.BaseTool;
import com.jd.genie.agent.util.SpringContextHolder;
import com.jd.genie.config.GenieConfig;
import com.jd.genie.model.response.AgentResponse;
import com.jd.genie.service.KnowledgeRAGService;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import okhttp3.*;
import org.springframework.context.ApplicationContext;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/**
 * 本地知识库检索工具
 * 用于查询已上传到本地知识库的文档内容
 */
@Slf4j
@Data
public class KnowledgeRAGTool implements BaseTool {
    
    private AgentContext agentContext;

    @Override
    public String getName() {
        return "knowledge_rag";
    }

    @Override
    public String getDescription() {
        String desc = "这是一个本地知识库检索工具，可以查询已上传到本地知识库的文档内容。当用户的问题涉及已上传的文件内容、文档知识时使用此工具。";
        GenieConfig genieConfig = SpringContextHolder.getApplicationContext().getBean(GenieConfig.class);
        return genieConfig.getKnowledgeRAGToolDesc().isEmpty() ? desc : genieConfig.getKnowledgeRAGToolDesc();
    }

    @Override
    public Map<String, Object> toParams() {
        GenieConfig genieConfig = SpringContextHolder.getApplicationContext().getBean(GenieConfig.class);
        if (!genieConfig.getKnowledgeRAGToolParams().isEmpty()) {
            return genieConfig.getKnowledgeRAGToolParams();
        }

        Map<String, Object> queryParam = new HashMap<>();
        queryParam.put("type", "string");
        queryParam.put("description", "用户的问题或查询内容");

        Map<String, Object> parameters = new HashMap<>();
        parameters.put("type", "object");
        Map<String, Object> properties = new HashMap<>();
        properties.put("query", queryParam);
        parameters.put("properties", properties);
        parameters.put("required", Arrays.asList("query"));

        return parameters;
    }

    @Override
    public Object execute(Object input) {
        long startTime = System.currentTimeMillis();
        try {
            Map<String, Object> params = (Map<String, Object>) input;
            String query = (String) params.getOrDefault("query", "");

            log.info("{} knowledge_rag tool execute, query={}", agentContext.getRequestId(), query);

            // 调用知识库查询接口
            Future<String> future = callKnowledgeRAG(query);
            Object result = future.get();
            
            log.info("{} knowledge_rag tool completed, duration={}ms", 
                    agentContext.getRequestId(), 
                    System.currentTimeMillis() - startTime);
            
            return result;
        } catch (Exception e) {
            log.error("{} knowledge_rag tool error", agentContext.getRequestId(), e);
            agentContext.getPrinter().send("tool_result", AgentResponse.ToolResult.builder()
                    .toolName("本地知识库")
                    .toolParam(new HashMap<>())
                    .toolResult("知识库查询失败: " + e.getMessage())
                    .build());
        }
        return null;
    }

    /**
     * 调用知识库查询API
     */
    public CompletableFuture<String> callKnowledgeRAG(String query) {
        CompletableFuture<String> future = new CompletableFuture<>();
        try {
            OkHttpClient client = new OkHttpClient.Builder()
                    .connectTimeout(60, TimeUnit.SECONDS)
                    .readTimeout(120, TimeUnit.SECONDS)
                    .writeTimeout(60, TimeUnit.SECONDS)
                    .callTimeout(120, TimeUnit.SECONDS)
                    .build();

            ApplicationContext applicationContext = SpringContextHolder.getApplicationContext();
            GenieConfig genieConfig = applicationContext.getBean(GenieConfig.class);
            
            // 获取知识库API地址
            String url = genieConfig.getKnowledgeRagUrl() + "/query";
            
            // 构造请求体
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("query", query);
            requestBody.put("request_id", agentContext.getRequestId());

            RequestBody body = RequestBody.create(
                    com.alibaba.fastjson.JSONObject.toJSONString(requestBody),
                    MediaType.parse("application/json")
            );

            log.info("{} knowledge_rag request: {}", agentContext.getRequestId(), 
                    com.alibaba.fastjson.JSONObject.toJSONString(requestBody));

            Request request = new Request.Builder()
                    .url(url)
                    .post(body)
                    .build();

            client.newCall(request).enqueue(new Callback() {
                @Override
                public void onFailure(Call call, IOException e) {
                    log.error("{} knowledge_rag request failed", agentContext.getRequestId(), e);
                    future.completeExceptionally(e);
                }

                @Override
                public void onResponse(Call call, Response response) {
                    try (ResponseBody responseBody = response.body()) {
                        if (!response.isSuccessful() || responseBody == null) {
                            log.error("{} knowledge_rag request error, code={}", 
                                    agentContext.getRequestId(), response.code());
                            future.completeExceptionally(new IOException("Unexpected response code: " + response.code()));
                            return;
                        }

                        BufferedReader reader = new BufferedReader(new InputStreamReader(responseBody.byteStream()));
                        StringBuilder resultBuilder = new StringBuilder();
                        String line;
                        while ((line = reader.readLine()) != null) {
                            resultBuilder.append(line);
                        }

                        String result = resultBuilder.toString();
                        log.info("{} knowledge_rag response: {}", agentContext.getRequestId(), result);

                        // 解析响应
                        com.alibaba.fastjson.JSONObject jsonResult = 
                                com.alibaba.fastjson.JSONObject.parseObject(result);
                        
                        // 获取知识库回答
                        String answer = jsonResult.getString("answer");
                        if (answer == null || answer.isEmpty()) {
                            answer = "知识库中没有找到相关信息";
                        }

                        // 发送工具结果
                        agentContext.getPrinter().send("tool_result", AgentResponse.ToolResult.builder()
                                .toolName("本地知识库")
                                .toolParam(Collections.singletonMap("query", query))
                                .toolResult(answer)
                                .build());

                        future.complete(answer);

                    } catch (Exception e) {
                        log.error("{} knowledge_rag response parse error", agentContext.getRequestId(), e);
                        future.completeExceptionally(e);
                    }
                }
            });
        } catch (Exception e) {
            log.error("{} knowledge_rag request build error", agentContext.getRequestId(), e);
            future.completeExceptionally(e);
        }

        return future;
    }
}