# coding=utf-8
# Copyright 2019 The TensorFlow Datasets Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Translation feature that supports multiple languages."""

import os
import six
import tensorflow as tf
from tensorflow_datasets.core.features import feature
from tensorflow_datasets.core.features import sequence_feature
from tensorflow_datasets.core.features import text_feature


class Translation(feature.FeaturesDict):
  """`FeatureConnector` for translations with fixed languages per example.

  Input: The Translate feature accepts a dictionary for each example mapping
    string language codes to string translations.

  Output: A dictionary mapping string language codes to translations as `Text`
    features.

  Example:
  At construction time:

  ```
  tfds.features.Translation(languages=['en', 'fr', 'de'])
  ```

  During data generation:

  ```
  yield self.info.encode_example({
      'en': 'the cat',
      'fr': 'le chat',
      'de': 'die katze'
  })
  ```

  Tensor returned by `.as_dataset()`:

  ```
  {
      'en': tf.Tensor(shape=(), dtype=tf.string, numpy='the cat'),
      'fr': tf.Tensor(shape=(), dtype=tf.string, numpy='le chat'),
      'de': tf.Tensor(shape=(), dtype=tf.string, numpy='die katze'),
  }
  ```
  """

  def __init__(self, languages, encoder=None, encoder_config=None):
    """Constructs a Translation FeatureConnector.

    Args:
      languages: `list<string>` Full list of languages codes.
      encoder: `tfds.features.text.TextEncoder` (optional), an encoder that can
        convert text to integers. If None, the text will be utf-8 byte-encoded.
      encoder_config: `tfds.features.text.TextEncoderConfig` (optional), needed
        if restoring from a file with `load_metadata`.
    """
    self._languages = set(languages)
    super(Translation, self).__init__(
        {l: text_feature.Text(encoder, encoder_config) for l in languages})

  @property
  def languages(self):
    """List of languages."""
    return sorted(self._languages)

  def save_metadata(self, data_dir, feature_name=None):
    """See base class for details."""
    # Save languages.
    languages_filepath = _get_languages_filepath(data_dir, feature_name)
    _write_languages_to_file(languages_filepath, self._languages)
    super(Translation, self).save_metadata(data_dir, feature_name)

  def load_metadata(self, data_dir, feature_name=None):
    """See base class for details."""
    # Restore languagess if defined
    languages_filepath = _get_languages_filepath(data_dir, feature_name)
    self._languages = _load_languages_from_file(languages_filepath)
    super(Translation, self).load_metadata(data_dir, feature_name)

  def _additional_repr_info(self):
    return {"languages": self.languages}


class TranslationVariableLanguages(sequence_feature.SequenceDict):
  """`FeatureConnector` for translations with variable languages per example.

  Input: The TranslationVariableLanguages feature accepts a dictionary for each
    example mapping string language codes to one or more string translations.
    The languages present may vary from example to example.

  Output:
    language: variable-length 1D tf.Tensor of tf.string language codes, sorted
      in ascending order.
    translation: variable-length 1D tf.Tensor of tf.string plain text
      translations, sorted to align with language codes.

  Example (fixed language list):
  At construction time:

  ```
  tfds.features.(languages=['en', 'fr', 'de'])
  ```

  During data generation:

  ```
  yield self.info.encode_example({
      'en': 'the cat',
      'fr': ['le chat', 'la chatte,']
      'de': 'die katze'
  })
  ```

  Tensor returned by `.as_dataset()`:

  ```
  {
      'language': tf.Tensor(
          shape=(4,), dtype=tf.string, numpy=array(['en', 'de', 'fr', 'fr']),
      'translation': tf.Tensor(
          shape=(4,), dtype=tf.string,
          numpy=array(['the cat', 'die katze', 'la chatte', 'le chat'])),
  }
  ```
  """

  def __init__(self, languages=None):
    """Constructs a Translation FeatureConnector.

    Args:
      languages: `list<string>` (optional), full list of languages codes if
        shared by all examples and known in advance.
    """
    # TODO(adarob): Add optional text encoders once `SequenceDict` adds support
    # for FixedVarLenFeatures.

    self._languages = set(languages) if languages else None
    super(TranslationVariableLanguages, self).__init__(
        feature_dict={
            "language": text_feature.Text(),
            "translation": text_feature.Text(),
        })

  @property
  def num_languages(self):
    """Number of languages or None, if not specified in advance."""
    return len(self._languages) if self._languages else None

  @property
  def languages(self):
    """List of languages or None, if not specified in advance."""
    return sorted(list(self._languages)) if self._languages else None

  def encode_example(self, translation_dict):
    if self.languages and set(translation_dict) - self._languages:
      raise ValueError(
          "Some languages in example ({0}) are not in valid set ({1}).".format(
              ", ".join(sorted(set(translation_dict) - self._languages)),
              ", ".join(self.languages)))

    # Convert dictionary into tuples, splitting out cases where there are
    # multiple translations for a single language.
    translation_tuples = []
    for l, t in translation_dict.items():
      if isinstance(t, six.string_types):
        translation_tuples.append((l, t))
      else:
        translation_tuples.extend([(l, u) for u in t])

    # Ensure translations are in ascending order by language code.
    languages, translations = zip(*sorted(translation_tuples))

    return super(TranslationVariableLanguages, self).encode_example(
        {"language": languages,
         "translation": translations})

  def save_metadata(self, data_dir, feature_name=None):
    """See base class for details."""
    # Save languages if defined.
    if self.languages:
      languages_filepath = _get_languages_filepath(data_dir, feature_name)
      _write_languages_to_file(languages_filepath, self._languages)
    super(TranslationVariableLanguages, self).save_metadata(
        data_dir, feature_name)

  def load_metadata(self, data_dir, feature_name=None):
    """See base class for details."""
    # Restore languagess if defined
    languages_filepath = _get_languages_filepath(data_dir, feature_name)
    if tf.io.gfile.exists(languages_filepath):
      self._languages = _load_languages_from_file(languages_filepath)
    super(TranslationVariableLanguages, self).load_metadata(
        data_dir, feature_name)

  def _additional_repr_info(self):
    return {"languages": self.languages}


def _get_languages_filepath(data_dir, feature_name):
  return os.path.join(data_dir, "{}.languages.txt".format(feature_name))


def _load_languages_from_file(languages_filepath):
  with tf.io.gfile.GFile(languages_filepath, "r") as f:
    return set(
        lang.strip()
        for lang in tf.compat.as_text(f.read()).split("\n")
        if lang.strip()  # Filter empty names
    )


def _write_languages_to_file(languages_filepath, languages):
  with tf.io.gfile.GFile(languages_filepath, "w") as f:
    f.write("\n".join(languages) + "\n")
