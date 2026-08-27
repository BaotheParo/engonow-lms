package com.engonow.lms.calibration.service.impl;

import com.engonow.lms.calibration.domain.entity.CalibrationCorpusItem;
import com.engonow.lms.calibration.domain.entity.CalibrationHumanRating;
import com.engonow.lms.calibration.domain.entity.CalibrationReferenceScore;
import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.ResolutionMethod;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.engonow.lms.calibration.dto.CalibrationHumanRatingDTO;
import com.engonow.lms.calibration.dto.CalibrationReferenceScoreDTO;
import com.engonow.lms.calibration.dto.CorpusItemCreateRequestDTO;
import com.engonow.lms.calibration.dto.CorpusItemResponseDTO;
import com.engonow.lms.calibration.dto.CorpusSnapshotResponseDTO;
import com.engonow.lms.calibration.dto.HumanRatingSubmitRequestDTO;
import com.engonow.lms.calibration.dto.ItemResolutionResponseDTO;
import com.engonow.lms.calibration.dto.SeniorAdjudicationRequestDTO;
import com.engonow.lms.calibration.repository.CalibrationCorpusItemRepository;
import com.engonow.lms.calibration.repository.CalibrationHumanRatingRepository;
import com.engonow.lms.calibration.repository.CalibrationReferenceScoreRepository;
import com.engonow.lms.calibration.service.CalibrationCorpusAdminService;
import com.engonow.lms.calibration.util.IccCalculator;
import com.engonow.lms.calibration.util.IccCalculator.IccResult;
import com.engonow.lms.writing.util.CambridgeRoundingUtil;
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
@Transactional
@RequiredArgsConstructor
@Slf4j
public class CalibrationCorpusAdminServiceImpl implements CalibrationCorpusAdminService {

    private final CalibrationCorpusItemRepository corpusItemRepository;
    private final CalibrationHumanRatingRepository humanRatingRepository;
    private final CalibrationReferenceScoreRepository referenceScoreRepository;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CorpusItemResponseDTO createCorpusItem(CorpusItemCreateRequestDTO request) {
        if (request.subsystem() == SubsystemType.WRITING && (request.essayText() == null || request.essayText().isBlank())) {
            throw new IllegalArgumentException("Writing corpus item must include non-blank essayText");
        }
        if (request.subsystem() == SubsystemType.SPEAKING && (request.sourceAudioUrl() == null || request.sourceAudioUrl().isBlank())) {
            throw new IllegalArgumentException("Speaking corpus item must include non-blank sourceAudioUrl");
        }

        CalibrationCorpusItem item = CalibrationCorpusItem.builder()
            .subsystem(request.subsystem())
            .taskType(request.taskType())
            .promptText(request.promptText())
            .essayText(request.essayText())
            .sourceAudioUrl(request.sourceAudioUrl())
            .sourceAudioDurationSeconds(request.sourceAudioDurationSeconds())
            .sourceTranscript(request.sourceTranscript())
            .targetBandStratum(request.targetBandStratum())
            .datasetSplit(DatasetSplit.UNASSIGNED)
            .intakeBatchId(request.intakeBatchId())
            .status(CorpusItemStatus.PENDING_RATING)
            .build();

        CalibrationCorpusItem saved = corpusItemRepository.save(item);
        log.info("[CALIBRATION INTAKE] Created new corpus item id={} subsystem={} stratum={}",
            saved.getId(), saved.getSubsystem(), saved.getTargetBandStratum());

        return mapToResponseDTO(saved);
    }

    @Override
    @Transactional(readOnly = true)
    public Page<CorpusItemResponseDTO> listCorpusItems(
        SubsystemType subsystem,
        DatasetSplit split,
        BandStratum stratum,
        CorpusItemStatus status,
        Pageable pageable
    ) {
        List<CalibrationCorpusItem> allItems = corpusItemRepository.findAll();

        List<CalibrationCorpusItem> filtered = allItems.stream()
            .filter(item -> subsystem == null || item.getSubsystem() == subsystem)
            .filter(item -> split == null || item.getDatasetSplit() == split)
            .filter(item -> stratum == null || item.getTargetBandStratum() == stratum)
            .filter(item -> status == null || item.getStatus() == status)
            .toList();

        int start = (int) pageable.getOffset();
        int end = Math.min((start + pageable.getPageSize()), filtered.size());
        List<CalibrationCorpusItem> pagedItems = (start <= end && start < filtered.size())
            ? filtered.subList(start, end)
            : List.of();

        // Access Logging for GATEKEEPER items to guard against developer overfitting
        for (CalibrationCorpusItem item : pagedItems) {
            if (item.getDatasetSplit() == DatasetSplit.GATEKEEPER) {
                log.warn("[GATEKEEPER BLIND ACCESS AUDIT] ItemId: {} Subsystem: {} Timestamp: {}",
                    item.getId(), item.getSubsystem(), Instant.now());
            }
        }

        List<CorpusItemResponseDTO> responseDTOs = pagedItems.stream()
            .map(this::mapToResponseDTO)
            .toList();

        return new PageImpl<>(responseDTOs, pageable, filtered.size());
    }

    @Override
    @Transactional(readOnly = true)
    public CorpusItemResponseDTO getCorpusItem(UUID id) {
        CalibrationCorpusItem item = corpusItemRepository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("CalibrationCorpusItem not found with ID: " + id));

        if (item.getDatasetSplit() == DatasetSplit.GATEKEEPER) {
            log.warn("[GATEKEEPER BLIND ACCESS AUDIT] ItemId: {} Subsystem: {} Timestamp: {}",
                item.getId(), item.getSubsystem(), Instant.now());
        }

        return mapToResponseDTO(item);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void submitHumanRating(UUID itemId, HumanRatingSubmitRequestDTO request) {
        CalibrationCorpusItem item = corpusItemRepository.findById(itemId)
            .orElseThrow(() -> new EntityNotFoundException("CalibrationCorpusItem not found with ID: " + itemId));

        // Uniqueness check: one rating per rater per criterion
        List<CalibrationHumanRating> existingRatings = humanRatingRepository.findByCorpusItemId(itemId);
        boolean duplicate = existingRatings.stream().anyMatch(r ->
            r.getRaterId().equals(request.raterId()) && r.getCriterion() == request.criterion()
        );

        if (duplicate) {
            throw new com.engonow.lms.calibration.exception.DuplicateRatingException(
                "Rater " + request.raterId() + " has already submitted a rating for criterion " + request.criterion()
            );
        }

        CalibrationHumanRating rating = CalibrationHumanRating.builder()
            .corpusItem(item)
            .raterId(request.raterId())
            .raterCredentialLevel(request.raterCredentialLevel())
            .criterion(request.criterion())
            .bandScore(request.bandScore())
            .transcriptFlaggedIncorrect(request.transcriptFlaggedIncorrect())
            .ratingNotes(request.ratingNotes())
            .build();

        try {
            humanRatingRepository.save(rating);
        } catch (org.springframework.dao.DataIntegrityViolationException ex) {
            throw new com.engonow.lms.calibration.exception.DuplicateRatingException(
                "Rater " + request.raterId() + " has already submitted a rating for criterion " + request.criterion(), ex
            );
        }

        if (item.getStatus() == CorpusItemStatus.PENDING_RATING) {
            item.setStatus(CorpusItemStatus.RATING_IN_PROGRESS);
            corpusItemRepository.save(item);
        }

        log.info("[CALIBRATION RATING] Submitted rating for item={} rater={} criterion={} score={}",
            itemId, request.raterId(), request.criterion(), request.bandScore());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ItemResolutionResponseDTO resolveItemCriterion(UUID itemId, EvaluationCriterion criterion) {
        CalibrationCorpusItem item = corpusItemRepository.findById(itemId)
            .orElseThrow(() -> new EntityNotFoundException("CalibrationCorpusItem not found with ID: " + itemId));

        List<CalibrationHumanRating> ratings = humanRatingRepository.findByCorpusItemId(itemId).stream()
            .filter(r -> r.getCriterion() == criterion)
            .toList();

        if (ratings.size() < 2) {
            throw new IllegalStateException("Minimum 2 ratings required to resolve criterion " + criterion + " (found " + ratings.size() + ")");
        }

        List<BigDecimal> scores = ratings.stream().map(CalibrationHumanRating::getBandScore).toList();
        BigDecimal minScore = scores.stream().min(BigDecimal::compareTo).orElseThrow();
        BigDecimal maxScore = scores.stream().max(BigDecimal::compareTo).orElseThrow();
        BigDecimal scoreDifference = maxScore.subtract(minScore);

        List<UUID> ratingIds = ratings.stream().map(CalibrationHumanRating::getId).toList();

        // Difference <= 0.5: Consensus reached
        if (scoreDifference.compareTo(new BigDecimal("0.5")) <= 0) {
            BigDecimal sum = scores.stream().reduce(BigDecimal.ZERO, BigDecimal::add);
            BigDecimal mean = sum.divide(BigDecimal.valueOf(scores.size()), 4, RoundingMode.HALF_UP);

            // Apply official Cambridge rounding to nearest 0.5 band
            BigDecimal referenceBand = CambridgeRoundingUtil.applyCambridgeRounding(mean);

            CalibrationReferenceScore referenceScore = CalibrationReferenceScore.builder()
                .corpusItem(item)
                .criterion(criterion)
                .referenceBand(referenceBand)
                .resolutionMethod(ResolutionMethod.MEAN_OF_RATERS)
                .contributingRatingIds(ratingIds)
                .discordant(false)
                .build();

            referenceScoreRepository.save(referenceScore);

            log.info("[CALIBRATION RESOLUTION] Consensus resolved for item={} criterion={} referenceBand={} method=MEAN_OF_RATERS",
                itemId, criterion, referenceBand);

            return new ItemResolutionResponseDTO(
                itemId,
                criterion,
                referenceBand,
                ResolutionMethod.MEAN_OF_RATERS,
                false,
                null,
                "Consensus resolved via mean of raters with Cambridge rounding"
            );
        }

        // Difference >= 1.0: Discordant item
        item.setStatus(CorpusItemStatus.DISCORDANT_PENDING_ADJUDICATION);
        corpusItemRepository.save(item);

        CalibrationReferenceScore provisionalRef = CalibrationReferenceScore.builder()
            .corpusItem(item)
            .criterion(criterion)
            .referenceBand(minScore)
            .resolutionMethod(ResolutionMethod.SINGLE_RATER_PROVISIONAL)
            .contributingRatingIds(ratingIds)
            .discordant(true)
            .build();

        referenceScoreRepository.save(provisionalRef);

        log.warn("[CALIBRATION DISCORDANCE] Discordant ratings detected for item={} criterion={} (scoreDiff={}). Set to DISCORDANT_PENDING_ADJUDICATION",
            itemId, criterion, scoreDifference);

        return new ItemResolutionResponseDTO(
            itemId,
            criterion,
            minScore,
            ResolutionMethod.SINGLE_RATER_PROVISIONAL,
            true,
            null,
            "Discordant ratings detected (score difference " + scoreDifference + " >= 1.0). Senior adjudication required."
        );
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public ItemResolutionResponseDTO adjudicateDiscordantItem(UUID itemId, SeniorAdjudicationRequestDTO request) {
        CalibrationCorpusItem item = corpusItemRepository.findById(itemId)
            .orElseThrow(() -> new EntityNotFoundException("CalibrationCorpusItem not found with ID: " + itemId));

        List<CalibrationHumanRating> ratings = humanRatingRepository.findByCorpusItemId(itemId).stream()
            .filter(r -> r.getCriterion() == request.criterion())
            .toList();

        List<UUID> ratingIds = ratings.stream().map(CalibrationHumanRating::getId).toList();

        CalibrationReferenceScore referenceScore = CalibrationReferenceScore.builder()
            .corpusItem(item)
            .criterion(request.criterion())
            .referenceBand(request.bindingScore())
            .resolutionMethod(ResolutionMethod.ADJUDICATED)
            .contributingRatingIds(ratingIds)
            .discordant(false)
            .adjudicatorId(request.adjudicatorId())
            .build();

        referenceScoreRepository.save(referenceScore);

        item.setStatus(CorpusItemStatus.ADJUDICATED);
        corpusItemRepository.save(item);

        log.info("[CALIBRATION ADJUDICATION] Senior examiner {} adjudicated item={} criterion={} bindingScore={}",
            request.adjudicatorId(), itemId, request.criterion(), request.bindingScore());

        return new ItemResolutionResponseDTO(
            itemId,
            request.criterion(),
            request.bindingScore(),
            ResolutionMethod.ADJUDICATED,
            false,
            null,
            "Item adjudicated by senior examiner"
        );
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void assignAndLockStratifiedSplit(UUID itemId, DatasetSplit targetSplit) {
        CalibrationCorpusItem item = corpusItemRepository.findById(itemId)
            .orElseThrow(() -> new EntityNotFoundException("CalibrationCorpusItem not found with ID: " + itemId));

        if (item.getSplitLockedAt() != null) {
            throw new ResponseStatusException(
                HttpStatus.CONFLICT,
                "dataset_split is locked for corpus item " + itemId + " (locked at " + item.getSplitLockedAt() + ")"
            );
        }

        Instant now = Instant.now();
        item.setDatasetSplit(targetSplit);
        item.setSplitAssignedAt(now);
        item.setSplitLockedAt(now);
        corpusItemRepository.save(item);

        log.info("[CALIBRATION SPLIT] Assigned and locked dataset_split={} for item={}", targetSplit, itemId);
    }

    @Override
    @Transactional(readOnly = true)
    public IccResult computeRaterPoolIcc(SubsystemType subsystem) {
        List<CalibrationHumanRating> ratings = humanRatingRepository.findBySubsystem(subsystem);

        Map<UUID, Map<UUID, Double>> ratingsMatrix = new HashMap<>();
        for (CalibrationHumanRating r : ratings) {
            ratingsMatrix
                .computeIfAbsent(r.getCorpusItem().getId(), k -> new HashMap<>())
                .put(r.getRaterId(), r.getBandScore().doubleValue());
        }

        return IccCalculator.calculateIcc31(ratingsMatrix);
    }

    @Override
    @Transactional(readOnly = true)
    public CorpusSnapshotResponseDTO getCorpusSnapshot() {
        List<CalibrationCorpusItem> items = corpusItemRepository.findAll();

        long total = items.size();
        long writing = items.stream().filter(i -> i.getSubsystem() == SubsystemType.WRITING).count();
        long speaking = items.stream().filter(i -> i.getSubsystem() == SubsystemType.SPEAKING).count();
        long tuning = items.stream().filter(i -> i.getDatasetSplit() == DatasetSplit.TUNING).count();
        long gatekeeper = items.stream().filter(i -> i.getDatasetSplit() == DatasetSplit.GATEKEEPER).count();
        long unassigned = items.stream().filter(i -> i.getDatasetSplit() == DatasetSplit.UNASSIGNED).count();

        Map<String, Long> stratumCounts = items.stream()
            .collect(Collectors.groupingBy(i -> i.getTargetBandStratum().getCode(), Collectors.counting()));

        Map<String, Long> statusCounts = items.stream()
            .collect(Collectors.groupingBy(i -> i.getStatus().name(), Collectors.counting()));

        return new CorpusSnapshotResponseDTO(
            total,
            writing,
            speaking,
            tuning,
            gatekeeper,
            unassigned,
            stratumCounts,
            statusCounts
        );
    }

    private CorpusItemResponseDTO mapToResponseDTO(CalibrationCorpusItem item) {
        List<CalibrationHumanRatingDTO> ratingDTOs = humanRatingRepository.findByCorpusItemId(item.getId()).stream()
            .map(r -> new CalibrationHumanRatingDTO(
                r.getId(),
                r.getRaterId(),
                r.getRaterCredentialLevel(),
                r.getCriterion(),
                r.getBandScore(),
                r.getTranscriptFlaggedIncorrect(),
                r.getRatingNotes(),
                r.getRatedAt()
            ))
            .toList();

        List<CalibrationReferenceScoreDTO> refScoreDTOs = referenceScoreRepository.findByCorpusItemId(item.getId()).stream()
            .map(s -> new CalibrationReferenceScoreDTO(
                s.getId(),
                s.getCriterion(),
                s.getReferenceBand(),
                s.getResolutionMethod(),
                s.getContributingRatingIds(),
                s.getIccAtResolution(),
                s.getDiscordant(),
                s.getAdjudicatorId(),
                s.getResolvedAt()
            ))
            .toList();

        return new CorpusItemResponseDTO(
            item.getId(),
            item.getSubsystem(),
            item.getTaskType(),
            item.getPromptText(),
            item.getEssayText(),
            item.getSourceAudioUrl(),
            item.getSourceAudioDurationSeconds(),
            item.getSourceTranscript(),
            item.getCalibrationHoldUntil(),
            item.getTargetBandStratum(),
            item.getDatasetSplit(),
            item.getSplitAssignedAt(),
            item.getSplitLockedAt(),
            item.getIntakeBatchId(),
            item.getStatus(),
            item.getCreatedAt(),
            item.getVersion(),
            ratingDTOs,
            refScoreDTOs
        );
    }
}
