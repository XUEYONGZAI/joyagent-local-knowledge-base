package com.jd.genie.service;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.jd.genie.agent.util.OkHttpUtil;
import com.jd.genie.model.req.KnowledgeRAGReq;
import lombok.extern.slf4j.Slf4j;
import okhttp3.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class KnowledgeRAGService {

    private static final MediaType JSON_TYPE = MediaType.get("application/json; charset=utf-8");
    private static final Long SSE_TIMEOUT = 60 * 1000L;

    @Value("${autobots.autoagent.knowledge_rag_url:http://127.0.0.1:8080/knowledge_rag}")
    private String knowledgeRagUrl;

    public String queryKnowledgeRAG(KnowledgeRAGReq req) throws IOException {
        req.setStream(false);

        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(60, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .writeTimeout(60, TimeUnit.SECONDS)
                .build();

        RequestBody body = RequestBody.create(
                JSON_TYPE,
                JSONObject.toJSONString(req)
        );

        Request request = new Request.Builder()
                .url(knowledgeRagUrl)
                .post(body)
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("知识库RAG调用失败: " + response);
            }

            String responseBody = response.body().string();
            JSONObject jsonResponse = JSON.parseObject(responseBody);

            if (jsonResponse.getInteger("code") != 200) {
                throw new IOException("知识库RAG调用失败: " + jsonResponse.getString("error"));
            }

            return jsonResponse.getString("data");
        }
    }

    public SseEmitter queryKnowledgeRAGStream(KnowledgeRAGReq req, SseEmitter emitter) {
        req.setStream(true);

        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(60, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.SECONDS)
                .writeTimeout(60, TimeUnit.SECONDS)
                .build();

        RequestBody body = RequestBody.create(
                JSON_TYPE,
                JSONObject.toJSONString(req)
        );

        Request request = new Request.Builder()
                .url(knowledgeRagUrl)
                .post(body)
                .build();

        client.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                log.error("知识库RAG流式调用失败: {}", e.getMessage(), e);
                try {
                    emitter.send(SseEmitter.event()
                            .name("error")
                            .data("调用失败: " + e.getMessage()));
                } catch (IOException ex) {
                    log.warn("SSE发送失败: {}", ex.getMessage());
                }
                emitter.complete();
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                ResponseBody responseBody = response.body();
                if (responseBody == null) {
                    log.error("知识库RAG响应体为空");
                    emitter.complete();
                    return;
                }

                if (!response.isSuccessful()) {
                    log.error("知识库RAG请求失败: {}", responseBody.string());
                    emitter.complete();
                    return;
                }

                try {
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(responseBody.byteStream())
                    );

                    String line;
                    while ((line = reader.readLine()) != null) {
                        if (line.startsWith("data:")) {
                            String data = line.substring(5);

                            if ("[DONE]".equals(data)) {
                                break;
                            }

                            if ("heartbeat".equals(data)) {
                                continue;
                            }

                            KnowledgeRAGResult result = JSON.parseObject(data, KnowledgeRAGResult.class);

                            String eventData = JSONObject.toJSONString(result);
                            emitter.send(SseEmitter.event()
                                    .name("message")
                                    .data(eventData));

                            if (Boolean.TRUE.equals(result.getIsFinal())) {
                                break;
                            }
                        }
                    }
                } catch (Exception e) {
                    log.error("处理知识库RAG响应异常: {}", e.getMessage(), e);
                } finally {
                    emitter.complete();
                }
            }
        });

        return emitter;
    }

    @lombok.Data
    public static class KnowledgeRAGResult {
        private String requestId;
        private String data;
        private Boolean isFinal;
        private String error;
    }
}