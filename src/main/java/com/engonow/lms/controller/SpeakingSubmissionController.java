package com.engonow.lms.controller;

import com.engonow.lms.dto.SpeakingSubmissionRequestDTO;
import com.engonow.lms.dto.SpeakingSubmissionResponseDTO;
import com.engonow.lms.service.SubmissionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/speaking")
@RequiredArgsConstructor
public class SpeakingSubmissionController {

    private final SubmissionService submissionService;

    @PostMapping({"/submit", "/submissions/submit"})
    public ResponseEntity<SpeakingSubmissionResponseDTO> submitSpeakingAttempt(
            @Valid @RequestBody SpeakingSubmissionRequestDTO request) {
        SpeakingSubmissionResponseDTO response = submissionService.submitSpeakingEvaluation(request);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(response);
    }
}
