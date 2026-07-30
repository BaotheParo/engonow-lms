package com.engonow.lms.controller;

import com.engonow.lms.dto.SubmissionResponseDTO;
import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.service.SubmissionService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/v1/submissions")
public class SubmissionController {

    private final SubmissionService submissionService;

    public SubmissionController(SubmissionService submissionService) {
        this.submissionService = submissionService;
    }

    @PostMapping("/scan")
    public ResponseEntity<SubmissionResponseDTO> scanOmrSheet(
            @RequestParam("examId") Long examId,
            @RequestParam("studentId") Long studentId,
            @RequestPart("file") MultipartFile file) {
        SubmissionResponseDTO response = submissionService.processOmrScan(examId, studentId, file);
        return new ResponseEntity<>(response, HttpStatus.CREATED);
    }

    @PostMapping("/speaking")
    public ResponseEntity<SpeakingSubmissionResponseDTO> submitSpeakingResponse(
            @Valid @RequestBody SpeakingSubmissionRequestDTO request) {
        SpeakingSubmissionResponseDTO response =
                submissionService.submitSpeakingEvaluation(request);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
    }
}
