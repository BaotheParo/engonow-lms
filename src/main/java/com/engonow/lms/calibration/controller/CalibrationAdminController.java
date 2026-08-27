package com.engonow.lms.calibration.controller;

import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.engonow.lms.calibration.dto.AssignSplitRequestDTO;
import com.engonow.lms.calibration.dto.CorpusItemCreateRequestDTO;
import com.engonow.lms.calibration.dto.CorpusItemResponseDTO;
import com.engonow.lms.calibration.dto.CorpusSnapshotResponseDTO;
import com.engonow.lms.calibration.dto.HumanRatingSubmitRequestDTO;
import com.engonow.lms.calibration.dto.ItemResolutionResponseDTO;
import com.engonow.lms.calibration.dto.SeniorAdjudicationRequestDTO;
import com.engonow.lms.calibration.service.CalibrationCorpusAdminService;
import com.engonow.lms.calibration.util.IccCalculator.IccResult;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/admin/calibration")
@RequiredArgsConstructor
@Tag(name = "Calibration & Ground Truth Admin", description = "Endpoints for managing the Golden Calibration Corpus, examiner ratings, and ICC analytics")
public class CalibrationAdminController {

    private final CalibrationCorpusAdminService calibrationAdminService;

    @PostMapping("/corpus-items")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Intake a new calibration corpus item")
    public ResponseEntity<CorpusItemResponseDTO> createCorpusItem(
            @Valid @RequestBody CorpusItemCreateRequestDTO request) {
        CorpusItemResponseDTO response = calibrationAdminService.createCorpusItem(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/corpus-items")
    @Operation(summary = "List calibration corpus items with filtering and pagination")
    public ResponseEntity<Page<CorpusItemResponseDTO>> listCorpusItems(
            @RequestParam(required = false) SubsystemType subsystem,
            @RequestParam(required = false) DatasetSplit split,
            @RequestParam(required = false) BandStratum stratum,
            @RequestParam(required = false) CorpusItemStatus status,
            @PageableDefault(size = 20) Pageable pageable) {
        Page<CorpusItemResponseDTO> response = calibrationAdminService.listCorpusItems(
                subsystem, split, stratum, status, pageable);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/corpus-items/{id}")
    @Operation(summary = "Get detailed calibration corpus item by ID")
    public ResponseEntity<CorpusItemResponseDTO> getCorpusItem(@PathVariable UUID id) {
        CorpusItemResponseDTO response = calibrationAdminService.getCorpusItem(id);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/corpus-items/{id}/ratings")
    @Operation(summary = "Submit an examiner human rating for a corpus item")
    public ResponseEntity<Void> submitHumanRating(
            @PathVariable UUID id,
            @Valid @RequestBody HumanRatingSubmitRequestDTO request) {
        calibrationAdminService.submitHumanRating(id, request);
        return ResponseEntity.ok().build();
    }

    @PostMapping("/corpus-items/{id}/resolve")
    @Operation(summary = "Resolve consensus reference score for a criterion")
    public ResponseEntity<ItemResolutionResponseDTO> resolveItemCriterion(
            @PathVariable UUID id,
            @RequestParam EvaluationCriterion criterion) {
        ItemResolutionResponseDTO response = calibrationAdminService.resolveItemCriterion(id, criterion);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/corpus-items/{id}/adjudicate")
    @Operation(summary = "Senior examiner binding adjudication for discordant items")
    public ResponseEntity<ItemResolutionResponseDTO> adjudicateDiscordantItem(
            @PathVariable UUID id,
            @Valid @RequestBody SeniorAdjudicationRequestDTO request) {
        ItemResolutionResponseDTO response = calibrationAdminService.adjudicateDiscordantItem(id, request);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/corpus-items/{id}/assign-split")
    @Operation(summary = "Assign and immutably lock dataset split (TUNING vs GATEKEEPER)")
    public ResponseEntity<Void> assignAndLockStratifiedSplit(
            @PathVariable UUID id,
            @Valid @RequestBody AssignSplitRequestDTO request) {
        calibrationAdminService.assignAndLockStratifiedSplit(id, request.targetSplit());
        return ResponseEntity.ok().build();
    }

    @GetMapping("/rater-pool/icc")
    @Operation(summary = "Calculate Two-Way Mixed Single-Score Consistency ICC(3,1) for rater pool")
    public ResponseEntity<IccResult> computeRaterPoolIcc(
            @RequestParam(required = false) SubsystemType subsystem) {
        IccResult result = calibrationAdminService.computeRaterPoolIcc(subsystem);
        return ResponseEntity.ok(result);
    }

    @GetMapping("/snapshot")
    @Operation(summary = "Get overall calibration corpus summary and stratification metrics")
    public ResponseEntity<CorpusSnapshotResponseDTO> getCorpusSnapshot() {
        CorpusSnapshotResponseDTO snapshot = calibrationAdminService.getCorpusSnapshot();
        return ResponseEntity.ok(snapshot);
    }
}
