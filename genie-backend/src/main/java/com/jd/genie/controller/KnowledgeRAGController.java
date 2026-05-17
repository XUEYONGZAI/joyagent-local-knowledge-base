package com.jd.genie.controller;

import com.jd.genie.model.req.KnowledgeRAGReq;
import com.jd.genie.service.KnowledgeRAGService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

@Slf4j
@RestController
@RequestMapping("/knowledge")
public class KnowledgeRAGController {

    private static final Long SSE_TIMEOUT = 60 * 60 * 1000L;

    @Autowired
    private KnowledgeRAGService knowledgeRAGService;

    @PostMapping(value = "/query", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter queryKnowledgeRAGStream(@RequestBody KnowledgeRAGReq req) {
        if (req.getRequestId() == null || req.getRequestId().isEmpty()) {
            req.setRequestId(UUID.randomUUID().toString());
        }

        log.info("知识库RAG流式查询请求: requestId={}, task={}, fileCount={}",
                req.getRequestId(), req.getTask(),
                req.getFilePaths() != null ? req.getFilePaths().size() : 0);

        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT);
        return knowledgeRAGService.queryKnowledgeRAGStream(req, emitter);
    }

    @PostMapping(value = "/querySync")
    public Map<String, Object> queryKnowledgeRAG(@RequestBody KnowledgeRAGReq req) {
        Map<String, Object> result = new HashMap<>();

        if (req.getRequestId() == null || req.getRequestId().isEmpty()) {
            req.setRequestId(UUID.randomUUID().toString());
        }

        log.info("知识库RAG同步查询请求: requestId={}, task={}, fileCount={}",
                req.getRequestId(), req.getTask(),
                req.getFilePaths() != null ? req.getFilePaths().size() : 0);

        try {
            String answer = knowledgeRAGService.queryKnowledgeRAG(req);
            result.put("code", 200);
            result.put("data", answer);
            result.put("requestId", req.getRequestId());
        } catch (Exception e) {
            log.error("知识库RAG查询异常: {}", e.getMessage(), e);
            result.put("code", 500);
            result.put("error", e.getMessage());
            result.put("requestId", req.getRequestId());
        }

        return result;
    }
}