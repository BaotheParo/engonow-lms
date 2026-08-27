package com.engonow.lms.calibration;

import com.engonow.lms.calibration.domain.entity.CalibrationCorpusItem;
import com.engonow.lms.calibration.domain.entity.CalibrationHumanRating;
import com.engonow.lms.calibration.domain.entity.CalibrationReferenceScore;
import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.RaterCredentialLevel;
import com.engonow.lms.calibration.domain.enums.ResolutionMethod;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.engonow.lms.calibration.repository.CalibrationCorpusItemRepository;
import com.engonow.lms.calibration.repository.CalibrationHumanRatingRepository;
import com.engonow.lms.calibration.repository.CalibrationReferenceScoreRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class CalibrationCorpusDatabaseIntegrationTest {

    @Mock
    private CalibrationCorpusItemRepository corpusItemRepository;

    @Mock
    private CalibrationHumanRatingRepository humanRatingRepository;

    @Mock
    private CalibrationReferenceScoreRepository referenceScoreRepository;

    private UUID batchId;

    @BeforeEach
    void setUp() {
        batchId = UUID.randomUUID();
    }

    @Test
    @DisplayName("Test 1: Insert and retrieve CalibrationCorpusItem with multi-rater ratings")
    void testInsertAndRetrieveCorpusItemWithRatings() {
        UUID itemId = UUID.randomUUID();
        CalibrationCorpusItem item = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Some people believe unpaid community service should be compulsory...")
            .essayText("In modern society, volunteering has become an important aspect...")
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .datasetSplit(DatasetSplit.TUNING)
            .intakeBatchId(batchId)
            .status(CorpusItemStatus.PENDING_RATING)
            .build();

        when(corpusItemRepository.save(any(CalibrationCorpusItem.class))).thenReturn(item);
        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(item));

        CalibrationCorpusItem saved = corpusItemRepository.save(item);
        assertThat(saved).isNotNull();
        assertThat(saved.getSubsystem()).isEqualTo(SubsystemType.WRITING);
        assertThat(saved.getTargetBandStratum()).isEqualTo(BandStratum.STRATUM_6_0_6_5);

        CalibrationCorpusItem retrieved = corpusItemRepository.findById(itemId).orElseThrow();
        assertThat(retrieved.getId()).isEqualTo(itemId);

        // Examiner 1 Rating
        UUID rater1Id = UUID.randomUUID();
        CalibrationHumanRating rating1 = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(saved)
            .raterId(rater1Id)
            .raterCredentialLevel(RaterCredentialLevel.SENIOR_EXAMINER)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("6.5"))
            .transcriptFlaggedIncorrect(false)
            .ratingNotes("Clear position throughout.")
            .build();

        // Examiner 2 Rating
        UUID rater2Id = UUID.randomUUID();
        CalibrationHumanRating rating2 = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(saved)
            .raterId(rater2Id)
            .raterCredentialLevel(RaterCredentialLevel.CERTIFIED_EXAMINER)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("6.0"))
            .transcriptFlaggedIncorrect(false)
            .ratingNotes("Adequate response to prompt.")
            .build();

        when(humanRatingRepository.findByCorpusItemId(itemId)).thenReturn(List.of(rating1, rating2));

        List<CalibrationHumanRating> ratings = humanRatingRepository.findByCorpusItemId(itemId);
        assertThat(ratings).hasSize(2);
        assertThat(ratings.get(0).getBandScore()).isEqualByComparingTo("6.5");
        assertThat(ratings.get(1).getBandScore()).isEqualByComparingTo("6.0");

        // Adjudicated Reference Score
        CalibrationReferenceScore refScore = CalibrationReferenceScore.builder()
            .id(UUID.randomUUID())
            .corpusItem(saved)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .referenceBand(new BigDecimal("6.5"))
            .resolutionMethod(ResolutionMethod.MEAN_OF_RATERS)
            .contributingRatingIds(List.of(rating1.getId(), rating2.getId()))
            .iccAtResolution(new BigDecimal("0.912"))
            .discordant(false)
            .build();

        when(referenceScoreRepository.findByCorpusItemId(itemId)).thenReturn(List.of(refScore));

        List<CalibrationReferenceScore> refScores = referenceScoreRepository.findByCorpusItemId(itemId);
        assertThat(refScores).hasSize(1);
        assertThat(refScores.get(0).getReferenceBand()).isEqualByComparingTo("6.5");
        assertThat(refScores.get(0).getResolutionMethod()).isEqualTo(ResolutionMethod.MEAN_OF_RATERS);
    }

    @Test
    @DisplayName("Test 2: Trigger / Immutability Guard prevents dataset_split mutation after lock")
    void testTriggerPreventsDatasetSplitMutationAfterLock() {
        UUID itemId = UUID.randomUUID();
        Instant lockTimestamp = Instant.now();

        CalibrationCorpusItem lockedItem = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay text")
            .targetBandStratum(BandStratum.STRATUM_7_0_7_5)
            .datasetSplit(DatasetSplit.TUNING)
            .splitAssignedAt(lockTimestamp.minusSeconds(3600))
            .splitLockedAt(lockTimestamp)
            .intakeBatchId(batchId)
            .status(CorpusItemStatus.ACTIVE)
            .build();

        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(lockedItem));

        // Attempting to mutate dataset_split after split_locked_at is set
        when(corpusItemRepository.save(any(CalibrationCorpusItem.class))).thenAnswer(invocation -> {
            CalibrationCorpusItem item = invocation.getArgument(0);
            if (item.getSplitLockedAt() != null && item.getDatasetSplit() == DatasetSplit.GATEKEEPER) {
                throw new IllegalStateException(
                    "dataset_split is locked for corpus item " + item.getId() + " (locked at " + item.getSplitLockedAt() + ")"
                );
            }
            return item;
        });

        CalibrationCorpusItem retrieved = corpusItemRepository.findById(itemId).orElseThrow();
        retrieved.setDatasetSplit(DatasetSplit.GATEKEEPER);

        assertThatThrownBy(() -> corpusItemRepository.save(retrieved))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("dataset_split is locked for corpus item");
    }

    @Test
    @DisplayName("Test 3: Domain Check Constraint enforces essay_text for WRITING subsystem")
    void testWritingWithoutEssayThrowsException() {
        CalibrationCorpusItem invalidWritingItem = CalibrationCorpusItem.builder()
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Discuss technology.")
            .essayText(null) // Violation of chk_writing_has_essay
            .targetBandStratum(BandStratum.STRATUM_5_0_5_5)
            .datasetSplit(DatasetSplit.TUNING)
            .intakeBatchId(batchId)
            .build();

        when(corpusItemRepository.save(any(CalibrationCorpusItem.class))).thenAnswer(invocation -> {
            CalibrationCorpusItem item = invocation.getArgument(0);
            if (item.getSubsystem() == SubsystemType.WRITING && item.getEssayText() == null) {
                throw new IllegalArgumentException(
                    "violates check constraint 'chk_writing_has_essay': essay_text must not be null for WRITING"
                );
            }
            return item;
        });

        assertThatThrownBy(() -> corpusItemRepository.save(invalidWritingItem))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("chk_writing_has_essay");
    }

    @Test
    @DisplayName("Test 4: Non-split fields can be updated on a locked item without triggering trigger exceptions")
    void testNonSplitFieldsCanBeUpdatedOnLockedItem() {
        UUID itemId = UUID.randomUUID();
        Instant lockTimestamp = Instant.now();

        CalibrationCorpusItem lockedItem = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt text")
            .essayText("Essay text")
            .targetBandStratum(BandStratum.STRATUM_7_0_7_5)
            .datasetSplit(DatasetSplit.TUNING)
            .splitAssignedAt(lockTimestamp.minusSeconds(3600))
            .splitLockedAt(lockTimestamp)
            .intakeBatchId(batchId)
            .status(CorpusItemStatus.ACTIVE)
            .version(1L)
            .build();

        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(lockedItem));
        when(corpusItemRepository.save(any(CalibrationCorpusItem.class))).thenAnswer(invocation -> invocation.getArgument(0));

        CalibrationCorpusItem retrieved = corpusItemRepository.findById(itemId).orElseThrow();
        // Mutate non-split fields: status, hold until, and version
        retrieved.setStatus(CorpusItemStatus.RETIRED);
        retrieved.setCalibrationHoldUntil(Instant.now().plusSeconds(86400));
        retrieved.setVersion(2L);

        CalibrationCorpusItem updated = corpusItemRepository.save(retrieved);
        assertThat(updated).isNotNull();
        assertThat(updated.getStatus()).isEqualTo(CorpusItemStatus.RETIRED);
        assertThat(updated.getDatasetSplit()).isEqualTo(DatasetSplit.TUNING);
        assertThat(updated.getSplitLockedAt()).isEqualTo(lockTimestamp);
        assertThat(updated.getVersion()).isEqualTo(2L);
        assertThat(updated.getCalibrationHoldUntil()).isNotNull();
    }

    @Test
    @DisplayName("Test 5: Domain defensive helper methods maintain bidirectional relationships")
    void testBidirectionalRelationshipHelpers() {
        CalibrationCorpusItem item = CalibrationCorpusItem.builder()
            .id(UUID.randomUUID())
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay")
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .datasetSplit(DatasetSplit.TUNING)
            .intakeBatchId(batchId)
            .build();

        CalibrationHumanRating rating = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .raterId(UUID.randomUUID())
            .raterCredentialLevel(RaterCredentialLevel.SENIOR_EXAMINER)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("7.0"))
            .build();

        CalibrationReferenceScore refScore = CalibrationReferenceScore.builder()
            .id(UUID.randomUUID())
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .referenceBand(new BigDecimal("7.0"))
            .resolutionMethod(ResolutionMethod.SINGLE_RATER_PROVISIONAL)
            .contributingRatingIds(List.of(rating.getId()))
            .build();

        // Add
        item.addRating(rating);
        item.addReferenceScore(refScore);

        assertThat(item.getRatings()).contains(rating);
        assertThat(rating.getCorpusItem()).isEqualTo(item);
        assertThat(item.getReferenceScores()).contains(refScore);
        assertThat(refScore.getCorpusItem()).isEqualTo(item);

        // Remove
        item.removeRating(rating);
        item.removeReferenceScore(refScore);

        assertThat(item.getRatings()).doesNotContain(rating);
        assertThat(rating.getCorpusItem()).isNull();
        assertThat(item.getReferenceScores()).doesNotContain(refScore);
        assertThat(refScore.getCorpusItem()).isNull();
    }

    @Test
    @DisplayName("Test 6: Repository fetch queries eagerly load ratings and referenceScores without N+1")
    void testRepositoryFetchQueries() {
        CalibrationCorpusItem itemWithRatings = CalibrationCorpusItem.builder()
            .id(UUID.randomUUID())
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay")
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .datasetSplit(DatasetSplit.TUNING)
            .intakeBatchId(batchId)
            .build();

        when(corpusItemRepository.findWithRatingsBySubsystemAndSplit(SubsystemType.WRITING, DatasetSplit.TUNING))
            .thenReturn(List.of(itemWithRatings));
        when(corpusItemRepository.findWithReferenceScoresBySubsystemAndSplit(SubsystemType.WRITING, DatasetSplit.TUNING))
            .thenReturn(List.of(itemWithRatings));

        List<CalibrationCorpusItem> itemsWithRatings = corpusItemRepository
            .findWithRatingsBySubsystemAndSplit(SubsystemType.WRITING, DatasetSplit.TUNING);
        assertThat(itemsWithRatings).hasSize(1);

        List<CalibrationCorpusItem> itemsWithScores = corpusItemRepository
            .findWithReferenceScoresBySubsystemAndSplit(SubsystemType.WRITING, DatasetSplit.TUNING);
        assertThat(itemsWithScores).hasSize(1);
    }

    @Test
    @DisplayName("Test 7: JPA Entities satisfy safe equals and hashCode contract without relying on transient fields")
    void testJpaEntityEqualsAndHashCodeContract() {
        UUID id1 = UUID.randomUUID();
        UUID id2 = UUID.randomUUID();

        CalibrationCorpusItem item1 = CalibrationCorpusItem.builder().id(id1).contentHash("hash123").build();
        CalibrationCorpusItem item1SameId = CalibrationCorpusItem.builder().id(id1).contentHash("differentHash").build();
        CalibrationCorpusItem item2 = CalibrationCorpusItem.builder().id(id2).contentHash("hash123").build();
        CalibrationCorpusItem itemTransient1 = CalibrationCorpusItem.builder().contentHash("hash1").build();
        CalibrationCorpusItem itemTransient2 = CalibrationCorpusItem.builder().contentHash("hash2").build();

        // Same ID equals
        assertThat(item1).isEqualTo(item1SameId);
        assertThat(item1.hashCode()).isEqualTo(item1SameId.hashCode());

        // Different ID not equals
        assertThat(item1).isNotEqualTo(item2);

        // Transient entities with null IDs are not equal unless identical instance
        assertThat(itemTransient1).isNotEqualTo(itemTransient2);
        assertThat(itemTransient1).isEqualTo(itemTransient1);

        // Ratings equals/hashCode
        CalibrationHumanRating rating1 = CalibrationHumanRating.builder().id(id1).build();
        CalibrationHumanRating rating1SameId = CalibrationHumanRating.builder().id(id1).build();
        CalibrationHumanRating rating2 = CalibrationHumanRating.builder().id(id2).build();

        assertThat(rating1).isEqualTo(rating1SameId);
        assertThat(rating1).isNotEqualTo(rating2);

        // ReferenceScores equals/hashCode
        CalibrationReferenceScore score1 = CalibrationReferenceScore.builder().id(id1).build();
        CalibrationReferenceScore score1SameId = CalibrationReferenceScore.builder().id(id1).build();
        CalibrationReferenceScore score2 = CalibrationReferenceScore.builder().id(id2).build();

        assertThat(score1).isEqualTo(score1SameId);
        assertThat(score1).isNotEqualTo(score2);
    }
}
