package com.engonow.lms.admin.dto;

import java.util.List;

public record DlqReplayResponseDTO(
    int messagesRead,
    int messagesReplayed,
    int messagesSkipped,
    List<String> replayedEventIds
) {}
