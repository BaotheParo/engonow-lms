package com.engonow.lms.service;

import com.engonow.lms.dto.SubmissionResponseDTO;
import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import org.springframework.web.multipart.MultipartFile;

public interface SubmissionService {
    SubmissionResponseDTO processOmrScan(Long examId, Long studentId, MultipartFile file);

    SpeakingSubmissionResponseDTO submitSpeakingEvaluation(
            SpeakingSubmissionRequestDTO request);
}
