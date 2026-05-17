package com.jd.genie.model.req;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class KnowledgeRAGReq {
    private String requestId;
    private String task;
    private List<String> filePaths;
    private Boolean stream;
    private StreamMode streamMode;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class StreamMode {
        private String mode;
    }
}