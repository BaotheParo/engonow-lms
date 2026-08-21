package com.engonow.lms.admin.service;

import com.engonow.lms.admin.dto.DlqReplayRequestDTO;
import com.engonow.lms.admin.dto.DlqReplayResponseDTO;

public interface KafkaDlqAdminService {

    /**
     * Inspects, filters, and replays messages from a dead letter queue back into a target topic.
     *
     * @param request the replay parameters including source DLQ, target topic, and message bounds
     * @return summary response containing read, replayed, and skipped counts
     */
    DlqReplayResponseDTO replayDlqMessages(DlqReplayRequestDTO request);
}
