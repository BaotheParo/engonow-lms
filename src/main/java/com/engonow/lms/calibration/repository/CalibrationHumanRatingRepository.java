package com.engonow.lms.calibration.repository;

import com.engonow.lms.calibration.domain.entity.CalibrationCorpusItem;
import com.engonow.lms.calibration.domain.entity.CalibrationHumanRating;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface CalibrationHumanRatingRepository extends JpaRepository<CalibrationHumanRating, UUID> {

    @Query("SELECT r FROM CalibrationHumanRating r WHERE r.corpusItem.id = :corpusItemId")
    List<CalibrationHumanRating> findByCorpusItemId(@Param("corpusItemId") UUID corpusItemId);

    @Query("SELECT r FROM CalibrationHumanRating r JOIN FETCH r.corpusItem c WHERE :subsystem IS NULL OR c.subsystem = :subsystem")
    List<CalibrationHumanRating> findBySubsystem(@Param("subsystem") SubsystemType subsystem);

    List<CalibrationHumanRating> findByCorpusItem(CalibrationCorpusItem corpusItem);
}
