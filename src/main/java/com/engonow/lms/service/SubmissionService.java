package com.engonow.lms.service;

import com.engonow.lms.dto.SubmissionResponseDTO;
import org.springframework.web.multipart.MultipartFile;

public interface SubmissionService {
    SubmissionResponseDTO processOmrScan(Long examId, Long studentId, MultipartFile file);
}
