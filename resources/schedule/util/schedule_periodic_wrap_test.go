// Copyright 2018 The Kubeflow Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package util

import (
	scheduleapi "github.com/kubeflow/pipelines/pkg/apis/schedule/v1alpha1"
	"github.com/stretchr/testify/assert"
	"k8s.io/apimachinery/pkg/apis/meta/v1"
	"math"
	"testing"
	"time"
)

func TestPeriodicScheduleWrap_getNextScheduledEpoch_StartDate_EndDate(t *testing.T) {
	// First job.
	schedule := NewPeriodicScheduleWrap(&scheduleapi.PeriodicSchedule{
		StartTime:      Metav1TimePointer(v1.NewTime(time.Unix(10*hour, 0).UTC())),
		EndTime:        Metav1TimePointer(v1.NewTime(time.Unix(11*hour, 0).UTC())),
		IntervalSecond: minute,
	})
	lastJobEpoch := int64(0)
	assert.Equal(t, int64(10*hour+minute),
		schedule.getNextScheduledEpoch(lastJobEpoch))

	// Not the first job.
	lastJobEpoch = int64(10*hour + 5*minute)
	assert.Equal(t, int64(10*hour+6*minute),
		schedule.getNextScheduledEpoch(lastJobEpoch))

	// Last job
	lastJobEpoch = int64(13 * hour)
	assert.Equal(t, int64(math.MaxInt64),
		schedule.getNextScheduledEpoch(lastJobEpoch))

}

func TestPeriodicScheduleWrap_getNextScheduledEpoch_PeriodOnly(t *testing.T) {
	schedule := NewPeriodicScheduleWrap(&scheduleapi.PeriodicSchedule{
		IntervalSecond: minute,
	})
	lastJobEpoch := int64(10 * hour)
	assert.Equal(t, int64(10*hour+minute),
		schedule.getNextScheduledEpoch(lastJobEpoch))
}

func TestPeriodicScheduleWrap_getNextScheduledEpoch_NoPeriod(t *testing.T) {
	schedule := NewPeriodicScheduleWrap(&scheduleapi.PeriodicSchedule{
		StartTime:      Metav1TimePointer(v1.NewTime(time.Unix(10*hour, 0).UTC())),
		EndTime:        Metav1TimePointer(v1.NewTime(time.Unix(11*hour, 0).UTC())),
		IntervalSecond: 0,
	})
	lastJobEpoch := int64(10 * hour)
	assert.Equal(t, int64(10*hour+second),
		schedule.getNextScheduledEpoch(lastJobEpoch))
}

func TestPeriodicScheduleWrap_GetNextScheduledEpoch(t *testing.T) {
	// There was a previous job.
	schedule := NewPeriodicScheduleWrap(&scheduleapi.PeriodicSchedule{
		StartTime:      Metav1TimePointer(v1.NewTime(time.Unix(10*hour+10*minute, 0).UTC())),
		EndTime:        Metav1TimePointer(v1.NewTime(time.Unix(11*hour, 0).UTC())),
		IntervalSecond: 60,
	})
	lastJobEpoch := int64(10*hour + 20*minute)
	defaultStartEpoch := int64(10*hour + 15*minute)
	assert.Equal(t, int64(10*hour+20*minute+minute),
		schedule.GetNextScheduledEpoch(&lastJobEpoch, defaultStartEpoch))

	// There is no previous job, falling back on the start date of the schedule.
	assert.Equal(t, int64(10*hour+10*minute+minute),
		schedule.GetNextScheduledEpoch(nil, defaultStartEpoch))

	// There is no previous job, no schedule start date, falling back on the
	// creation date of the workflow.
	schedule = NewPeriodicScheduleWrap(&scheduleapi.PeriodicSchedule{
		EndTime:        Metav1TimePointer(v1.NewTime(time.Unix(11*hour, 0).UTC())),
		IntervalSecond: 60,
	})
	assert.Equal(t, int64(10*hour+15*minute+minute),
		schedule.GetNextScheduledEpoch(nil, defaultStartEpoch))
}
