; Targets: tree-sitter-python via tree-sitter-language-pack >=0.13.0
; Capture convention: @def.name for definitions, @ref.name for references

;; Definitions
(class_definition
  name: (identifier) @def.name) @definition.class

(function_definition
  name: (identifier) @def.name) @definition.function

;; References — function/method calls
(call
  function: [
      (identifier) @ref.name
      (attribute
        attribute: (identifier) @ref.name)
  ]) @reference.call

;; References — imported names
;; `from x import y, z` captures y, z
;; `import x` captures x
(import_from_statement
  name: (dotted_name
    (identifier) @ref.name))

(import_statement
  name: (dotted_name
    (identifier) @ref.name))
