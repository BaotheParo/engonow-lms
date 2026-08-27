package com.engonow.lms.calibration;

import com.engonow.lms.calibration.domain.entity.CalibrationCorpusItem;
import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.engonow.lms.calibration.dto.CorpusSnapshotResponseDTO;
import com.engonow.lms.calibration.repository.CalibrationCorpusItemRepository;
import com.engonow.lms.calibration.repository.CalibrationHumanRatingRepository;
import com.engonow.lms.calibration.repository.CalibrationReferenceScoreRepository;
import com.engonow.lms.calibration.service.CalibrationCorpusAdminService;
import com.engonow.lms.calibration.service.impl.CalibrationCorpusAdminServiceImpl;
import com.engonow.lms.calibration.util.IccCalculator.IccResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class MAEAcceptanceGatekeeperIntegrationTest {

    @Mock
    private CalibrationCorpusItemRepository itemRepository;

    @Mock
    private CalibrationHumanRatingRepository ratingRepository;

    @Mock
    private CalibrationReferenceScoreRepository scoreRepository;

    private CalibrationCorpusAdminService adminService;

    @BeforeEach
    void setUp() {
        adminService = new CalibrationCorpusAdminServiceImpl(
            itemRepository,
            ratingRepository,
            scoreRepository
        );
    }

    @Test
    @DisplayName("Gatekeeper Test 1: Rater Pool ICC meets >= 0.80 reliability threshold")
    void testGatekeeperPreconditions_RaterPoolIccReliability() {
        UUID item1Id = UUID.randomUUID();
        UUID item2Id = UUID.randomUUID();
        UUID item3Id = UUID.randomUUID();
        UUID raterA = UUID.randomUUID();
        UUID raterB = UUID.randomUUID();

        CalibrationCorpusItem item1 = CalibrationCorpusItem.builder().id(item1Id).subsystem(SubsystemType.WRITING).build();
        CalibrationCorpusItem item2 = CalibrationCorpusItem.builder().id(item2Id).subsystem(SubsystemType.WRITING).build();
        CalibrationCorpusItem item3 = CalibrationCorpusItem.builder().id(item3Id).subsystem(SubsystemType.WRITING).build();

        var r1 = com.engonow.lms.calibration.domain.entity.CalibrationHumanRating.builder()
            .corpusItem(item1).raterId(raterA).bandScore(java.math.BigDecimal.valueOf(5.0)).build();
        var r2 = com.engonow.lms.calibration.domain.entity.CalibrationHumanRating.builder()
            .corpusItem(item1).raterId(raterB).bandScore(java.math.BigDecimal.valueOf(5.0)).build();
        var r3 = com.engonow.lms.calibration.domain.entity.CalibrationHumanRating.builder()
            .corpusItem(item2).raterId(raterA).bandScore(java.math.BigDecimal.valueOf(7.0)).build();
        var r4 = com.engonow.lms.calibration.domain.entity.CalibrationHumanRating.builder()
            .corpusItem(item2).raterId(raterB).bandScore(java.math.BigDecimal.valueOf(7.5)).build();
        var r5 = com.engonow.lms.calibration.domain.entity.CalibrationHumanRating.builder()
            .corpusItem(item3).raterId(raterA).bandScore(java.math.BigDecimal.valueOf(8.5)).build();
        var r6 = com.engonow.lms.calibration.domain.entity.CalibrationHumanRating.builder()
            .corpusItem(item3).raterId(raterB).bandScore(java.math.BigDecimal.valueOf(8.5)).build();

        when(ratingRepository.findBySubsystem(SubsystemType.WRITING)).thenReturn(List.of(r1, r2, r3, r4, r5, r6));

        IccResult result = adminService.computeRaterPoolIcc(SubsystemType.WRITING);
        assertThat(result).isNotNull();
        assertThat(result.isValid()).isTrue();
        assertThat(result.icc()).isGreaterThanOrEqualTo(0.80);
    }

    @Test
    @DisplayName("Gatekeeper Test 2: Gatekeeper dataset split locking enforces immutability and blocks mutation with 409 Conflict")
    void testGatekeeperSplitLocking_PreventsMutation() {
        UUID itemId = UUID.randomUUID();
        CalibrationCorpusItem item = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt test")
            .contentHash("hash123")
            .targetBandStratum(BandStratum.STRATUM_7_0_7_5)
            .datasetSplit(DatasetSplit.GATEKEEPER)
            .splitLockedAt(Instant.now()) // Already locked!
            .status(CorpusItemStatus.ACTIVE)
            .build();

        when(itemRepository.findById(itemId)).thenReturn(Optional.of(item));

        // Attempting to assign target split to already locked item MUST fail with ResponseStatusException (409 Conflict)
        assertThatThrownBy(() -> adminService.assignAndLockStratifiedSplit(itemId, DatasetSplit.TUNING))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("409 CONFLICT");
    }

    @Test
    @DisplayName("Gatekeeper Test 3: Gatekeeper Snapshot ensures item stratification and counts")
    void testGatekeeperSnapshot_ValidatesIntegrity() {
        CalibrationCorpusItem item1 = CalibrationCorpusItem.builder()
            .id(UUID.randomUUID())
            .subsystem(SubsystemType.WRITING)
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .datasetSplit(DatasetSplit.TUNING)
            .status(CorpusItemStatus.ACTIVE)
            .build();

        CalibrationCorpusItem item2 = CalibrationCorpusItem.builder()
            .id(UUID.randomUUID())
            .subsystem(SubsystemType.WRITING)
            .targetBandStratum(BandStratum.STRATUM_7_0_7_5)
            .datasetSplit(DatasetSplit.GATEKEEPER)
            .status(CorpusItemStatus.ACTIVE)
            .build();

        when(itemRepository.findAll()).thenReturn(List.of(item1, item2));

        CorpusSnapshotResponseDTO snapshot = adminService.getCorpusSnapshot();
        assertThat(snapshot).isNotNull();
        assertThat(snapshot.totalItems()).isEqualTo(2L);
        assertThat(snapshot.tuningItems()).isEqualTo(1L);
        assertThat(snapshot.gatekeeperItems()).isEqualTo(1L);
        assertThat(snapshot.writingItems()).isEqualTo(2L);
        assertThat(snapshot.stratumCounts()).containsEntry("6.0-6.5", 1L);
        assertThat(snapshot.stratumCounts()).containsEntry("7.0-7.5", 1L);
    }
}
