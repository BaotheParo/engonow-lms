package com.engonow.lms.calibration.service;

import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import com.engonow.lms.calibration.dto.CorpusItemCreateRequestDTO;
import com.engonow.lms.calibration.dto.CorpusItemResponseDTO;
import com.engonow.lms.calibration.dto.CorpusSnapshotResponseDTO;
import com.engonow.lms.calibration.dto.HumanRatingSubmitRequestDTO;
import com.engonow.lms.calibration.dto.ItemResolutionResponseDTO;
import com.engonow.lms.calibration.dto.SeniorAdjudicationRequestDTO;
import com.engonow.lms.calibration.util.IccCalculator.IccResult;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface CalibrationCorpusAdminService {

    CorpusItemResponseDTO createCorpusItem(CorpusItemCreateRequestDTO request);

    Page<CorpusItemResponseDTO> listCorpusItems(
        SubsystemType subsystem,
        DatasetSplit split,
        BandStratum stratum,
        CorpusItemStatus status,
        Pageable pageable
    );

    CorpusItemResponseDTO getCorpusItem(UUID id);

    void submitHumanRating(UUID itemId, HumanRatingSubmitRequestDTO request);

    ItemResolutionResponseDTO resolveItemCriterion(UUID itemId, EvaluationCriterion criterion);

    ItemResolutionResponseDTO adjudicateDiscordantItem(UUID itemId, SeniorAdjudicationRequestDTO request);

    void assignAndLockStratifiedSplit(UUID itemId, DatasetSplit targetSplit);

    IccResult computeRaterPoolIcc(SubsystemType subsystem);

    CorpusSnapshotResponseDTO getCorpusSnapshot();
}
