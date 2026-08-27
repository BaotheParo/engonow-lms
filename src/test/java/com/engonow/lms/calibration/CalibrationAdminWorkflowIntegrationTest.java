package com.engonow.lms.calibration;

import com.engonow.lms.calibration.controller.CalibrationAdminController;
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
import com.engonow.lms.calibration.dto.AssignSplitRequestDTO;
import com.engonow.lms.calibration.dto.CorpusItemCreateRequestDTO;
import com.engonow.lms.calibration.dto.HumanRatingSubmitRequestDTO;
import com.engonow.lms.calibration.dto.ItemResolutionResponseDTO;
import com.engonow.lms.calibration.dto.SeniorAdjudicationRequestDTO;
import com.engonow.lms.calibration.repository.CalibrationCorpusItemRepository;
import com.engonow.lms.calibration.repository.CalibrationHumanRatingRepository;
import com.engonow.lms.calibration.repository.CalibrationReferenceScoreRepository;
import com.engonow.lms.calibration.service.impl.CalibrationCorpusAdminServiceImpl;
import com.engonow.lms.calibration.util.IccCalculator;
import com.engonow.lms.calibration.util.IccCalculator.IccResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.Spy;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
public class CalibrationAdminWorkflowIntegrationTest {

    private MockMvc mockMvc;

    @Spy
    private ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

    @Mock
    private CalibrationCorpusItemRepository corpusItemRepository;

    @Mock
    private CalibrationHumanRatingRepository humanRatingRepository;

    @Mock
    private CalibrationReferenceScoreRepository referenceScoreRepository;

    private CalibrationCorpusAdminServiceImpl adminService;

    @BeforeEach
    void setUp() {
        adminService = new CalibrationCorpusAdminServiceImpl(
            corpusItemRepository,
            humanRatingRepository,
            referenceScoreRepository
        );

        CalibrationAdminController controller = new CalibrationAdminController(adminService);
        mockMvc = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    @DisplayName("Test 1: Mathematical precision of Two-Way Mixed Single-Score Consistency ICC(3,1)")
    void testIccCalculatorMathematicalPrecision() {
        // Construct 4 items x 2 raters balanced matrix
        UUID item1 = UUID.randomUUID();
        UUID item2 = UUID.randomUUID();
        UUID item3 = UUID.randomUUID();
        UUID item4 = UUID.randomUUID();

        UUID raterA = UUID.randomUUID();
        UUID raterB = UUID.randomUUID();

        Map<UUID, Map<UUID, Double>> matrix = new HashMap<>();
        matrix.put(item1, Map.of(raterA, 6.0, raterB, 6.5));
        matrix.put(item2, Map.of(raterA, 5.0, raterB, 5.5));
        matrix.put(item3, Map.of(raterA, 7.0, raterB, 7.5));
        matrix.put(item4, Map.of(raterA, 8.0, raterB, 8.0));

        IccResult result = IccCalculator.calculateIcc31(matrix);

        assertThat(result.isValid()).isTrue();
        assertThat(result.itemCount()).isEqualTo(4);
        assertThat(result.raterCount()).isEqualTo(2);
        // High agreement across items should produce strong positive ICC (> 0.90)
        assertThat(result.icc()).isGreaterThan(0.90);
        assertThat(result.raterMeanDeviations()).containsKey(raterA);
        assertThat(result.raterMeanDeviations()).containsKey(raterB);
    }

    @Test
    @DisplayName("Test 2: Happy Path - Ingest item, submit 2 agreeing ratings, resolve consensus via Mean of Raters")
    void testHappyPathRatingAndAgreementResolution() throws Exception {
        UUID itemId = UUID.randomUUID();
        UUID batchId = UUID.randomUUID();

        // 1. Intake Item via REST
        CorpusItemCreateRequestDTO createRequest = new CorpusItemCreateRequestDTO(
            SubsystemType.WRITING,
            "TASK2",
            "Discuss the benefits of public transportation.",
            "Investing in railways and buses significantly reduces urban emissions and traffic congestion...",
            null,
            null,
            null,
            BandStratum.STRATUM_6_0_6_5,
            batchId
        );

        when(corpusItemRepository.save(any(CalibrationCorpusItem.class))).thenAnswer(i -> {
            CalibrationCorpusItem item = i.getArgument(0);
            item.setId(itemId);
            return item;
        });

        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(createRequest)))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(itemId.toString()))
            .andExpect(jsonPath("$.subsystem").value("WRITING"))
            .andExpect(jsonPath("$.targetBandStratum").value("6.0-6.5"));

        // 2. Submit Ratings: Examiner 1 (Score 6.0) & Examiner 2 (Score 6.5)
        CalibrationCorpusItem corpusItem = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay")
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .status(CorpusItemStatus.PENDING_RATING)
            .build();

        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(corpusItem));

        UUID rater1 = UUID.randomUUID();
        UUID rater2 = UUID.randomUUID();

        HumanRatingSubmitRequestDTO rating1Req = new HumanRatingSubmitRequestDTO(
            rater1,
            RaterCredentialLevel.CERTIFIED_EXAMINER,
            EvaluationCriterion.TASK_RESPONSE,
            new BigDecimal("6.0"),
            false,
            "Good response"
        );

        when(humanRatingRepository.findByCorpusItemId(itemId)).thenReturn(List.of());

        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/ratings")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(rating1Req)))
            .andExpect(status().isOk());

        // 3. Resolve Criterion -> (6.0 + 6.5) / 2 = 6.25 -> Cambridge rounds to 6.5
        CalibrationHumanRating r1 = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(corpusItem)
            .raterId(rater1)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("6.0"))
            .build();

        CalibrationHumanRating r2 = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(corpusItem)
            .raterId(rater2)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("6.5"))
            .build();

        when(humanRatingRepository.findByCorpusItemId(itemId)).thenReturn(List.of(r1, r2));

        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/resolve")
                .param("criterion", "TASK_RESPONSE"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.corpusItemId").value(itemId.toString()))
            .andExpect(jsonPath("$.criterion").value("TASK_RESPONSE"))
            .andExpect(jsonPath("$.referenceBand").value(6.5))
            .andExpect(jsonPath("$.resolutionMethod").value("MEAN_OF_RATERS"))
            .andExpect(jsonPath("$.requiresAdjudicator").value(false));

        verify(referenceScoreRepository).save(any(CalibrationReferenceScore.class));
    }

    @Test
    @DisplayName("Test 3: Discordant rating (diff >= 1.0) triggers senior adjudication and binding score")
    void testDiscordantRatingTriggersSeniorAdjudication() throws Exception {
        UUID itemId = UUID.randomUUID();
        CalibrationCorpusItem corpusItem = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay")
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .status(CorpusItemStatus.RATING_IN_PROGRESS)
            .build();

        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(corpusItem));

        // Rater 1: 5.0, Rater 2: 6.5 -> Difference 1.5 >= 1.0 (Discordant)
        CalibrationHumanRating r1 = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(corpusItem)
            .raterId(UUID.randomUUID())
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("5.0"))
            .build();

        CalibrationHumanRating r2 = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(corpusItem)
            .raterId(UUID.randomUUID())
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("6.5"))
            .build();

        when(humanRatingRepository.findByCorpusItemId(itemId)).thenReturn(List.of(r1, r2));

        // 1. Resolve -> Discordant flag set, requiresAdjudicator == true
        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/resolve")
                .param("criterion", "TASK_RESPONSE"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requiresAdjudicator").value(true));

        assertThat(corpusItem.getStatus()).isEqualTo(CorpusItemStatus.DISCORDANT_PENDING_ADJUDICATION);

        // 2. Senior Adjudication: Senior Examiner binds score to 6.0
        UUID seniorExaminerId = UUID.randomUUID();
        SeniorAdjudicationRequestDTO adjudicationRequest = new SeniorAdjudicationRequestDTO(
            seniorExaminerId,
            EvaluationCriterion.TASK_RESPONSE,
            new BigDecimal("6.0"),
            "Adjudicated score based on well-developed main ideas."
        );

        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/adjudicate")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(adjudicationRequest)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.corpusItemId").value(itemId.toString()))
            .andExpect(jsonPath("$.referenceBand").value(6.0))
            .andExpect(jsonPath("$.resolutionMethod").value("ADJUDICATED"))
            .andExpect(jsonPath("$.requiresAdjudicator").value(false));

        assertThat(corpusItem.getStatus()).isEqualTo(CorpusItemStatus.ADJUDICATED);
    }

    @Test
    @DisplayName("Test 4: Stratified Split Assignment and Immutability Lock returns 409 on second mutation")
    void testSplitAssignmentAndLockingThrows409OnMutation() throws Exception {
        UUID itemId = UUID.randomUUID();
        CalibrationCorpusItem corpusItem = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay")
            .targetBandStratum(BandStratum.STRATUM_7_0_7_5)
            .datasetSplit(DatasetSplit.UNASSIGNED)
            .status(CorpusItemStatus.ACTIVE)
            .build();

        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(corpusItem));

        // 1. Assign and Lock to TUNING -> Success
        AssignSplitRequestDTO tuningRequest = new AssignSplitRequestDTO(DatasetSplit.TUNING);
        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/assign-split")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(tuningRequest)))
            .andExpect(status().isOk());

        assertThat(corpusItem.getDatasetSplit()).isEqualTo(DatasetSplit.TUNING);
        assertThat(corpusItem.getSplitLockedAt()).isNotNull();

        // 2. Attempt second mutation to GATEKEEPER -> Throws HTTP 409 Conflict
        AssignSplitRequestDTO gatekeeperRequest = new AssignSplitRequestDTO(DatasetSplit.GATEKEEPER);
        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/assign-split")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(gatekeeperRequest)))
            .andExpect(status().isConflict());
    }

    @Test
    @DisplayName("Test 5: Defensive guard in IccCalculator handles zero variance / invalid denominator safely")
    void testIccCalculatorZeroVarianceGuard() {
        UUID item1 = UUID.randomUUID();
        UUID item2 = UUID.randomUUID();
        UUID raterA = UUID.randomUUID();
        UUID raterB = UUID.randomUUID();

        // Identical scores across all items and raters -> zero variance between items & error
        Map<UUID, Map<UUID, Double>> zeroVarianceMatrix = Map.of(
            item1, Map.of(raterA, 6.0, raterB, 6.0),
            item2, Map.of(raterA, 6.0, raterB, 6.0)
        );

        IccResult result = IccCalculator.calculateIcc31(zeroVarianceMatrix);
        assertThat(result.isValid()).isFalse();
        assertThat(result.icc()).isEqualTo(0.0);
        assertThat(result.diagnosticMessage()).contains("Zero variance or invalid denominator detected across rater pool");
    }

    @Test
    @DisplayName("Test 6: Duplicate rating submission throws DuplicateRatingException and maps to HTTP 409 Conflict")
    void testDuplicateRatingSubmissionThrows409Conflict() throws Exception {
        UUID itemId = UUID.randomUUID();
        UUID raterId = UUID.randomUUID();

        CalibrationCorpusItem corpusItem = CalibrationCorpusItem.builder()
            .id(itemId)
            .subsystem(SubsystemType.WRITING)
            .taskType("TASK2")
            .promptText("Prompt")
            .essayText("Essay")
            .targetBandStratum(BandStratum.STRATUM_6_0_6_5)
            .status(CorpusItemStatus.PENDING_RATING)
            .build();

        when(corpusItemRepository.findById(itemId)).thenReturn(Optional.of(corpusItem));

        CalibrationHumanRating existingRating = CalibrationHumanRating.builder()
            .id(UUID.randomUUID())
            .corpusItem(corpusItem)
            .raterId(raterId)
            .criterion(EvaluationCriterion.TASK_RESPONSE)
            .bandScore(new BigDecimal("6.5"))
            .build();

        when(humanRatingRepository.findByCorpusItemId(itemId)).thenReturn(List.of(existingRating));

        HumanRatingSubmitRequestDTO duplicateReq = new HumanRatingSubmitRequestDTO(
            raterId,
            RaterCredentialLevel.CERTIFIED_EXAMINER,
            EvaluationCriterion.TASK_RESPONSE,
            new BigDecimal("7.0"),
            false,
            "Duplicate rating attempt"
        );

        mockMvc.perform(post("/api/v1/admin/calibration/corpus-items/" + itemId + "/ratings")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(duplicateReq)))
            .andExpect(status().isConflict());
    }
}
